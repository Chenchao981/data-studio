from apps.desktop.rendering import configure_rendering,RecoveryBudget


def test_rendering_is_process_local_and_keeps_existing_options(monkeypatch):
    monkeypatch.setenv('QTWEBENGINE_CHROMIUM_FLAGS','--remote-debugging-port=12345')
    monkeypatch.setenv('QT_QUICK_BACKEND','default')
    import os
    configure_rendering('auto')
    assert os.environ['QT_QUICK_BACKEND']=='default'
    configure_rendering('software');configure_rendering('software')
    assert os.environ['QT_QUICK_BACKEND']=='software'
    assert os.environ['QTWEBENGINE_CHROMIUM_FLAGS'].split()==['--remote-debugging-port=12345','--disable-gpu']


def test_recovery_budget_prevents_reload_loop():
    now=[0];budget=RecoveryBudget(lambda:now[0])
    assert budget.take()
    assert not budget.take()
    now[0]=59;assert not budget.take()
    now[0]=60;assert budget.take()
