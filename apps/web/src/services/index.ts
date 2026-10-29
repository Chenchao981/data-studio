import {DesktopDataService} from './desktop';
import {MockDataService} from './mock';
export const service=location.protocol==='studio:'?new DesktopDataService():new MockDataService();
// WebDataService will implement the same contract after PYMS API approval (M3).
