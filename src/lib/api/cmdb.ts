// Routes API calls to the right backend at build time. UI / hooks import
// only this module — they do not know which backend they are talking to.
import { API_MODE } from "./mode";
import * as cloud from "./cmdb.cloud";
import * as internal from "./cmdb.internal";

const impl = API_MODE === "internal" ? internal : cloud;

export const listServers = impl.listServers;
export const getServer = impl.getServer;
export const createServer = impl.createServer;
export const updateServer = impl.updateServer;
export const deleteServer = impl.deleteServer;
export const batchDeleteServers = impl.batchDeleteServers;
export const getBmcStatus = impl.getBmcStatus;
export const refreshBmcStatus = impl.refreshBmcStatus;
export const listParts = impl.listParts;
export const getPart = impl.getPart;
export const createPart = impl.createPart;
export const updatePart = impl.updatePart;
export const deletePart = impl.deletePart;
export const listMovements = impl.listMovements;
export const createMovement = impl.createMovement;
export const listPartItems = impl.listPartItems;
export const getPartItem = impl.getPartItem;
export const lookupItemBySn = impl.lookupItemBySn;
export const lookupItemsBySns = impl.lookupItemsBySns;
export const createPartItems = impl.createPartItems;
export const updatePartItem = impl.updatePartItem;
export const deletePartItem = impl.deletePartItem;
export const listInstalledItems = impl.listInstalledItems;
export const listUsers = impl.listUsers;
export const createUser = impl.createUser;
export const updateUser = impl.updateUser;
export const deleteUser = impl.deleteUser;
export const resetUserPassword = impl.resetUserPassword;
export const changeMyPassword = impl.changeMyPassword;
export const unlockUser = impl.unlockUser;
export const listAuditLogs = impl.listAuditLogs;
export const signInWithUsername = impl.signInWithUsername;
export const signOut = impl.signOut;
export const fetchCurrentProfile = impl.fetchCurrentProfile;
export const subscribeAuthChanges = impl.subscribeAuthChanges;
