"""CP-style native selector shared by files and folders."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from PySide6.QtCore import QDir, QModelIndex, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileSystemModel,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from python_core.paths import desktop_directory as get_desktop_path

def set_widget_property(widget,key,value):
    widget.setProperty(key,value)
    widget.style().unpolish(widget);widget.style().polish(widget)


class InputSourceSelectionError(ValueError):
    """Raised when a GUI selection does not match the supported source modes."""


def validate_input_source_selection(
    paths: Sequence[str | Path],
) -> tuple[Path, ...]:
    """One selection can contain regular files and directories; detect by stat."""
    normalized=[];seen=set()
    from python_core.paths import local_path
    for raw in paths:
        try:path=local_path(str(raw))
        except (OSError,ValueError) as exc:raise InputSourceSelectionError(str(exc)) from exc
        key=str(path).casefold()
        if key in seen:continue
        if not (path.is_file() or path.is_dir()):raise InputSourceSelectionError('请选择普通文件或文件夹')
        seen.add(key);normalized.append(path)
    if not normalized:raise InputSourceSelectionError('请选择文件或文件夹')
    if len(normalized)>100:raise InputSourceSelectionError('每次最多选择100项')
    return tuple(normalized)


def resolve_start_directory(start_path: str | Path | None) -> Path:
    """Resolve an existing directory suitable for opening the selector."""

    fallback = Path(get_desktop_path())
    if not start_path:
        return fallback

    candidate = Path(str(start_path).strip().strip('"')).expanduser()
    if candidate.is_file():
        candidate = candidate.parent
    return candidate if candidate.is_dir() else fallback


class InputSourceDialog(QDialog):
    """CP-style one-window browser for local files and folders."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        title: str = "选择数据来源",
        start_path: str | Path | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("inputSourceDialog")
        self.selected_sources: tuple[Path, ...] = ()
        self.current_directory = resolve_start_directory(start_path)
        self.setWindowTitle(title)
        self.resize(860, 560)
        self.setMinimumSize(720, 460)
        self.setStyleSheet("""
            QDialog {background:#f7f9fd;color:#24324b;font-size:14px}
            QLabel {color:#334155} QLabel[tone="error"] {color:#be123c}
            QLineEdit,QTreeView,QComboBox {background:white;color:#24324b;border:1px solid #d7e0ec;border-radius:5px;padding:7px;selection-background-color:#dbeafe;selection-color:#173c78}
            QPushButton {background:white;color:#245ac1;border:1px solid #cddaf0;border-radius:5px;padding:8px 13px}
            QPushButton:hover {background:#e7efff} QPushButton:disabled {color:#94a3b8;background:#f1f5f9}
            QHeaderView::section {background:#edf2fa;color:#334155;border:0;padding:8px}
        """)
        self._build_ui()
        self._set_current_directory(self.current_directory)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        hint = QLabel(
            "文件和文件夹在同一窗口选择，可按 Ctrl / Shift 多选。双击文件夹进入，点击底部按钮选择。"
        )
        hint.setWordWrap(True)
        hint.setProperty("role", "helpText")
        layout.addWidget(hint)

        navigation = QHBoxLayout()
        self.desktop_button = QPushButton("桌面")
        self.desktop_button.clicked.connect(self._go_desktop)
        self.up_button = QPushButton("上一级")
        self.up_button.clicked.connect(self._go_up)

        self.drive_combo = QComboBox()
        self.drive_combo.setMinimumWidth(85)
        for drive in QDir.drives():
            drive_path = drive.absoluteFilePath()
            self.drive_combo.addItem(drive_path, drive_path)
        self.drive_combo.activated.connect(self._go_drive)

        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("粘贴文件夹路径进入；粘贴文件路径后按 Enter 选用")
        self.path_edit.returnPressed.connect(self._go_to_typed_path)
        self.go_button = QPushButton("转到")
        self.go_button.clicked.connect(self._go_to_typed_path)

        navigation.addWidget(self.desktop_button)
        navigation.addWidget(self.up_button)
        navigation.addWidget(self.drive_combo)
        navigation.addWidget(self.path_edit, 1)
        navigation.addWidget(self.go_button)
        layout.addLayout(navigation)

        self.model = QFileSystemModel(self)
        self.model.setReadOnly(True)
        self.model.setFilter(QDir.AllDirs | QDir.Files | QDir.NoDotAndDotDot)
        self.model.setNameFilters(["*"])
        self.model.setNameFilterDisables(False)

        self.source_view = QTreeView()
        self.source_view.setModel(self.model)
        self.source_view.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.source_view.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.source_view.setRootIsDecorated(False)
        self.source_view.setItemsExpandable(False)
        self.source_view.setAlternatingRowColors(True)
        self.source_view.setSortingEnabled(True)
        self.source_view.sortByColumn(0, Qt.AscendingOrder)
        self.source_view.setColumnWidth(0, 360)
        self.source_view.doubleClicked.connect(self._open_item)
        self.source_view.selectionModel().selectionChanged.connect(
            self._update_selection_summary
        )
        layout.addWidget(self.source_view, 1)

        self.selection_summary = QLabel("尚未选择数据来源")
        self.selection_summary.setProperty("tone", "muted")
        layout.addWidget(self.selection_summary)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        self.current_folder_button = self.button_box.addButton(
            "使用当前文件夹", QDialogButtonBox.ActionRole
        )
        self.current_folder_button.clicked.connect(self._use_current_folder)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        self.ok_button = self.button_box.button(QDialogButtonBox.Ok)
        self.ok_button.setText("确定")
        self.ok_button.setEnabled(False)
        self.button_box.button(QDialogButtonBox.Cancel).setText("取消")
        layout.addWidget(self.button_box)

    def _set_current_directory(self, directory: Path) -> None:
        directory = directory.resolve()
        self.current_directory = directory
        self.path_edit.setText(str(directory))
        root_index = self.model.setRootPath(str(directory))
        self.source_view.setRootIndex(root_index)
        self.source_view.clearSelection()
        self._update_selection_summary()

        drive_root = directory.anchor.casefold()
        for index in range(self.drive_combo.count()):
            value_root = Path(str(self.drive_combo.itemData(index))).anchor.casefold()
            if value_root == drive_root:
                self.drive_combo.blockSignals(True)
                self.drive_combo.setCurrentIndex(index)
                self.drive_combo.blockSignals(False)
                break

    def _selected_paths(self) -> list[Path]:
        return [
            Path(self.model.filePath(index))
            for index in self.source_view.selectionModel().selectedRows(0)
        ]

    def _update_selection_summary(self, *_args) -> None:
        paths = self._selected_paths()
        if not paths:
            self.selection_summary.setText("尚未选择数据来源")
            set_widget_property(self.selection_summary, "tone", "muted")
            self.ok_button.setEnabled(False)
            return

        try:
            validated = validate_input_source_selection(
                paths,
            )
        except InputSourceSelectionError as exc:
            self.selection_summary.setText(str(exc))
            set_widget_property(self.selection_summary, "tone", "error")
            self.ok_button.setEnabled(False)
            return

        if len(validated)==1 and validated[0].is_dir():
            summary = f"将使用文件夹：{validated[0]}"
        else:
            summary = f"已选择 {len(validated)} 项（文件 / 文件夹）"
        self.selection_summary.setText(summary)
        set_widget_property(self.selection_summary, "tone", "success")
        self.ok_button.setEnabled(True)

    def _go_desktop(self) -> None:
        self._set_current_directory(resolve_start_directory(None))

    def _go_up(self) -> None:
        parent = self.current_directory.parent
        if parent != self.current_directory:
            self._set_current_directory(parent)

    def _go_drive(self, index: int) -> None:
        drive_path = self.drive_combo.itemData(index)
        if drive_path:
            self._set_current_directory(Path(str(drive_path)))

    def _go_to_typed_path(self) -> None:
        typed_path = Path(self.path_edit.text().strip().strip('"')).expanduser()
        if typed_path.is_dir():
            self._set_current_directory(typed_path)
            return
        if typed_path.is_file():
            self.selected_sources=validate_input_source_selection([typed_path])
            super().accept();return
        QMessageBox.warning(self, "路径无效", f"文件或文件夹不存在：\n{typed_path}")

    def _open_item(self, index: QModelIndex) -> None:
        path = Path(self.model.filePath(index))
        if path.is_dir():
            self._set_current_directory(path)
        elif path.is_file():
            self.selected_sources = validate_input_source_selection(
                [path],
            )
            super().accept()

    def _use_current_folder(self) -> None:
        self.selected_sources = validate_input_source_selection(
            [self.current_directory],
        )
        super().accept()

    def accept(self) -> None:
        try:
            self.selected_sources = validate_input_source_selection(
                self._selected_paths(),
            )
        except InputSourceSelectionError as exc:
            QMessageBox.warning(self, "选择无效", str(exc))
            return
        super().accept()


def select_input_sources(
    parent: QWidget,
    *,
    title: str,
    start_path: str | Path | None = None,
) -> tuple[Path, ...]:
    """Open the shared selector and return the accepted data sources."""

    dialog = InputSourceDialog(
        parent,
        title=title,
        start_path=start_path,
    )
    if dialog.exec() == QDialog.Accepted:
        return dialog.selected_sources
    return ()
