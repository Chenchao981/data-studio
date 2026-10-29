Unicode true
RequestExecutionLevel user
SetCompressor /SOLID lzma
SetCompressorDictSize 32
SetDatablockOptimize off
!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "x64.nsh"
!include "WinVer.nsh"

!define APP_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\NCE.DataStudio"
Name "Data Studio ${APP_VERSION}"
OutFile "${SETUP_FILE}"
InstallDir "$LOCALAPPDATA\Programs\NCE\Data Studio"
InstallDirRegKey HKCU "${APP_KEY}" "InstallLocation"
BrandingText "Data Studio · CP/FT 本地数据工作台"
VIProductVersion "${APP_VERSION}.0"
VIAddVersionKey /LANG=2052 "ProductName" "Data Studio"
VIAddVersionKey /LANG=2052 "FileDescription" "Data Studio 安装程序"
VIAddVersionKey /LANG=2052 "FileVersion" "${APP_VERSION}"
VIAddVersionKey /LANG=2052 "ProductVersion" "${APP_VERSION}"
VIAddVersionKey /LANG=2052 "LegalCopyright" "Wuxi NCE Power Co., Ltd."

!define MUI_ICON "${ICON_FILE}"
!define MUI_UNICON "${ICON_FILE}"
!define MUI_ABORTWARNING
!define MUI_WELCOMEPAGE_TITLE "欢迎安装 Data Studio"
!define MUI_WELCOMEPAGE_TEXT "CP / FT 本地数据清洗与分析工作台。$\r$\n$\r$\n本安装包已包含所需运行环境，无需另外安装 Python 或 Anaconda。$\r$\n$\r$\n安装前请先关闭正在运行的 Data Studio。"
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_RUN "$INSTDIR\DesktopDataStudio.exe"
!define MUI_FINISHPAGE_RUN_TEXT "打开 Data Studio"
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "SimpChinese"

Function .onInit
  SetShellVarContext current
  ${IfNot} ${RunningX64}
    MessageBox MB_ICONSTOP "本安装包需要 Windows 10 或 Windows 11 的 64 位系统。" /SD IDOK
    SetErrorLevel 2
    Abort
  ${EndIf}
  ${IfNot} ${AtLeastWin10}
    MessageBox MB_ICONSTOP "请在 Windows 10 或 Windows 11 上安装。" /SD IDOK
    SetErrorLevel 2
    Abort
  ${EndIf}
FunctionEnd

Section "Data Studio" SEC_APP
  SetShellVarContext current
  ; Opening for writing fails if Windows still has the executable running.
  IfFileExists "$INSTDIR\DesktopDataStudio.exe" 0 copy_files
  ClearErrors
  FileOpen $0 "$INSTDIR\DesktopDataStudio.exe" a
  IfErrors app_in_use
  FileClose $0
  Goto copy_files
app_in_use:
  MessageBox MB_ICONSTOP "请先关闭正在运行的 Data Studio，然后重新安装。" /SD IDOK
  SetErrorLevel 2
  Abort
copy_files:
  !include "${PAYLOAD_INCLUDE}"
  SetOutPath "$INSTDIR"
  File /oname=install-manifest.json "${MANIFEST_FILE}"
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  CreateDirectory "$SMPROGRAMS\Data Studio"
  CreateShortcut "$SMPROGRAMS\Data Studio\Data Studio.lnk" "$INSTDIR\DesktopDataStudio.exe" "" "$INSTDIR\DesktopDataStudio.exe"
  CreateShortcut "$SMPROGRAMS\Data Studio\卸载 Data Studio.lnk" "$INSTDIR\Uninstall.exe"
  CreateShortcut "$DESKTOP\Data Studio.lnk" "$INSTDIR\DesktopDataStudio.exe" "" "$INSTDIR\DesktopDataStudio.exe"
  WriteRegStr HKCU "${APP_KEY}" "DisplayName" "Data Studio"
  WriteRegStr HKCU "${APP_KEY}" "DisplayVersion" "${APP_VERSION}"
  WriteRegStr HKCU "${APP_KEY}" "Publisher" "新洁能股份有限公司"
  WriteRegStr HKCU "${APP_KEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${APP_KEY}" "DisplayIcon" '$\"$INSTDIR\DesktopDataStudio.exe$\"'
  WriteRegStr HKCU "${APP_KEY}" "UninstallString" '$\"$INSTDIR\Uninstall.exe$\"'
  WriteRegStr HKCU "${APP_KEY}" "QuietUninstallString" '$\"$INSTDIR\Uninstall.exe$\" /S'
  WriteRegDWORD HKCU "${APP_KEY}" "NoModify" 1
  WriteRegDWORD HKCU "${APP_KEY}" "NoRepair" 1
  WriteRegDWORD HKCU "${APP_KEY}" "EstimatedSize" ${INSTALLED_KB}
SectionEnd

Function un.onInit
  IfFileExists "$INSTDIR\DesktopDataStudio.exe" 0 done
  ClearErrors
  FileOpen $0 "$INSTDIR\DesktopDataStudio.exe" a
  IfErrors locked
  FileClose $0
  Goto done
locked:
  MessageBox MB_ICONSTOP "请先关闭 Data Studio，再卸载程序。" /SD IDOK
  SetErrorLevel 2
  Abort
done:
FunctionEnd

Section "Uninstall"
  SetShellVarContext current
  ; Only remove files included by this installer, never a recursive user folder.
  !include "${UNINSTALL_INCLUDE}"
  Delete "$INSTDIR\install-manifest.json"
  Delete "$INSTDIR\Uninstall.exe"
  Delete "$DESKTOP\Data Studio.lnk"
  Delete "$SMPROGRAMS\Data Studio\Data Studio.lnk"
  Delete "$SMPROGRAMS\Data Studio\卸载 Data Studio.lnk"
  RMDir "$SMPROGRAMS\Data Studio"
  DeleteRegKey HKCU "${APP_KEY}"
  RMDir "$INSTDIR"
SectionEnd
