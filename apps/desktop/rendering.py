"""Process-local rendering policy; configure before importing Qt WebEngine."""
import os
import time


def configure_rendering(mode):
    if mode not in {'software','auto'}:raise ValueError('Unknown rendering mode')
    if mode=='software':
        flags=os.environ.get('QTWEBENGINE_CHROMIUM_FLAGS','')
        if '--disable-gpu' not in flags.split():flags=(flags+' --disable-gpu').strip()
        os.environ['QTWEBENGINE_CHROMIUM_FLAGS']=flags
        os.environ['QT_QUICK_BACKEND']='software'


class RecoveryBudget:
    """One automatic reload per minute; repeated faults need a deliberate retry."""
    def __init__(self,clock=time.monotonic):
        self.clock=clock;self.last=None

    def take(self):
        now=self.clock()
        if self.last is not None and now-self.last<60:return False
        self.last=now
        return True
