#!/usr/bin/env python3
import sys
import connections
import argparse
import getpass
import json
import datetime
import time

class Logger(object):
    def __init__(self, file, mode='a', verbose=False):
        try:
            self.fp = open(file, mode)
        except:
            print("Error opening %s for Logger" %file)
            sys.exit()
        self.verbose=verbose

    def log(self, entry, jsonData=False, jheader=True, verbose=False):
        t = str(datetime.datetime.utcnow())
        verboseChange=False
        if verbose:
            if not self.verbose:
                self.verbose=True
                verboseChange=True
        if not entry:
            if self.verbose:
                print("%s - " %t)
            self.fp.write("%s - " %t + "\n")
        elif not jsonData or not isinstance(entry,dict):
            if self.verbose:
                print("%s %s" %(t,entry))
            self.fp.write("%s %s" %(t, entry) + "\n")
        else:
            if self.verbose:
                print("%s - JSON data:" %t)
                print(json.dumps(entry,indent=4))
            if jheader:
                self.fp.write("%s - JSON data:" %t + "\n")
            json.dump(obj=entry, fp=self.fp, indent=4)
            self.fp.write("\n")
                      
        if verboseChange:
            self.verbose=False

    def close(self):
        self.fp.close()


'''
Holds all the 
'''
class NSXT(object):
    def __init__(self, mp, logger, listApi=None,
                 domain='default', site='default',
                 enforcementPoint='default'):

        self.mp=mp
        self.listApi=listApi
        self.domain=site
        self.ep=enforcementPoint
        self.logger=logger

    def __pageHandler(self, api):
        '''
        Handle multipage results by merging them into one dictionary
        '''
        firstLoop=True
        cursor = None
        result={}

        while firstLoop or cursor:
            fistLoop = False
            if '?' in api:
                url = '%s&cursor=%s' % (api,cursor) if cursor else api
            else:
                url = '%s?cursor=%s' % (api,cursor) if cursor else api

            r = self.mp.get(api=url, verbose=False,trial=False)
            if result:
                result['results'].extend(r['results'])
            else:
                result = r
            if 'cursor' not in r:
                return result
            elif int(r['cursor']) == r['result_count']:
                return result
            else:
                cursor=r['cursor']
                
    def submitApi(self, api, data, logger, args):
        req = {}
        req['method'] = "PATCH"
        req['api'] = api
        req['timestamp'] = str(datetime.datetime.utcnow())
        r = self.mp.patch(api=api,data=data,verbose=True, trial=False)
        if not r:
            logger.log("WARN: patch API %s returned no status" %api)
            req['status_code'] = 0
            req['message'] = None
        elif r.status_code != 200:
            req['status_code'] = r.status_code
            req['message'] = json.loads(r.text)
            logger.log("WARN: API failed with code %s" % str(r.status_code))
            logger.log("WARN: API failure text: %s" % r.text)
        else:
            req['status_code'] = r.status_code
            req['message'] = r.text

        return req
    

    def jsonPrint(self, data, header=None, indent=4, brief=False):
        '''
        Takes dictionary and print output to stdout
        '''
        if data and not isinstance(data,dict):
            self.logger.log("Data not a valid dictionary")
            return
        if header and not brief:
            self.logger.log(header)
        if data:
            if 'results' not in data.keys() or not brief:
                self.logger.log(data, True)
            else:
                if header:
                    self.logger.log("%30s %30s %-s" %("name","id","path"))
                    self.logger.log("%30s %30s %-s" %("----------","----------", "----------"))
                for i in data['results']:
                    self.logger.log("%30s %30s %-s" %(i['display_name'],
                                            i['id'],
                                            i['path'] if 'path' in i.keys() else "-"))
    def removeStatusFromSearchList(self, data, fields=["status"]):
        if 'results' not in data:
            return data
        for d in data['results']:
            for f in fields:
                if f in d:
                    del d[f]
        return data

    def list(self, api=None, brief=False, verbose=True,
             removeSearch=False, searchFields=['status'],
             header=None):
        '''
        Returns of a list of NSX objects with api.  The return result will combine
        multipage results into one
        '''
        if not api:
            if self.listApi:
                api = self.listApi
            else:
                logger.log("Calling list() without providing API")
                return None
        r = self.__pageHandler(api=api)
        if removeSearch and '/search/query' in api:
            r = self.removeStatusFromSearchList(data=r, fields=searchFields)
        if verbose:
            logger.log("API: GET %s" %self.mp.normalizeGmLmApi(api))
            self.jsonPrint(data=r, brief=brief, header=header)
        return r
        
    def findByName(self, name, field='display_name', removeSearch=True,
                   api=None, data=None, display=True,brief=False):
        '''
        Find an nsxobject by display_name
        '''
        if not data:
            if not api:
                if self.listApi:
                    api=self.listApi
            if not api:
                self.logger.log ("Calling list with no API specified")
                return None
            data = self.list(api=api,display=False, removeSearch=removeSearch)
        obj = None
        for o in data['results']:
            if o[field] == name:
                obj = o
                break
        if obj and display:
            if brief:
                self.logger.log("%d. Name: %s" %(i,obj[field]))
                self.logger.log("    Id: %s" %(obj['id']))
            else:
                self.jsonPrint(data=obj)
        return obj
    
    def findById(self, id, api=None, data=None, display=True,brief=False, removeSearch=True):
        '''
        Find an nsxobject by id
        '''
        if not data:
            if not api:
                if self.listApi:
                    api=self.listApi
            if not api:
                self.logger.log ("Calling list with no API specified")
                return None
        data = self.list(api=api,display=False, removeSearch=removeSearch)
        obj = None

        for o in data['results']:
            if o['id'] == id:
                obj = o
                break
        if obj and display:
            if brief:
                self.logger.log("%d. Name: %s" %(i,obj['display_name']))
                self.logger.log("   Id: %s" %(obj['id']))
            else:
                self.jsonPrint(data=obj)
        return obj

    def getIdByName(self, name, api=None,data=None,display=True):
        '''
        Return the ID of an object found by display_name
        '''
        r = self.findByName(name=name, api=api,data=data,display=False)
        if r:
            return r['id']
        
    def getPathByName(self, name, api=None, data=None, display=True):
        '''
        Return the Policy Path of an object found by display_name
        '''
        if not api:
            api=self.listApi

        obj = self.findByName(api=api,name=name, data=data, display=False)
        if obj:
            if display:
                self.logger.log(obj['path'])
            return obj['path']
        return None

    def getPathById(self, id, api=None, data=None, display=True):
        '''
        Return the Policy path of an object found by id
        '''
        if not api:
            api=self.listApi

        obj = self.findById(api=api,id=id,data=data, display=False)
        if obj:
            if display:
                self.logger.log(obj['path'])
            return obj['path']
        return None

def parseParameters():
    parser=argparse.ArgumentParser()
    parser.add_argument("--mc", required=True,
                        help="IP or FQDN of the NSX node running Migration Coordinator")
    parser.add_argument("--mcUser", required=False,
                        default="admin",
                        help="User name to connect to Migration Coordinator, default: admin")
    parser.add_argument("--mcPassword", required=False,
                        help="Password for mcUser")

    parser.add_argument("--nsx", required=True,
                        help="IP or FQDN of the destination NSX Manager")
    parser.add_argument("--nsxUser", required=False,
                        default="admin",
                        help="User name to connect to destination NSX Manger")
    parser.add_argument("--nsxPassword", required=False,
                        help="Password for nsxUser")
    parser.add_argument("--storageJson", required=False,
                        default="/var/log/migration-coordinator/v2t/storage.json",
                        help="storage.json file from Migration coordinator")
    parser.add_argument("--segmentMap", required=True,
                        help="JSON file mapping destination segments to segments on MC")
    parser.add_argument("--portMaps", required=True, nargs="*",
                        help="List of map files  with VM portmappings")
    parser.add_argument("--migrationData", required=True,
                        help="File to store migration data and auditing outptus")
    parser.add_argument("--logfile", required=True,
                        help="Filename to store logs")
    parser.add_argument("--prefix", required=True,
                        help="Prefix to pretend to all object IDs and names")
    parser.add_argument("--serviceNameCheck", required=False,
                        action='store_true',
                        help="Enable service and context profile name comparison")
    parser.add_argument("--updateServiceName", required=False,
                        action='store_true',
                        help="Prepend migrated services and context profile names with prefix")
    args = parser.parse_args()
    return args


def readPortMappings(logger, args):
    data={}
    data['VmLports'] = {}
    data['VmSegPortPaths'] = {}
    data['VnicSegPortPaths'] = {}

    for fname in args.portMaps:
        logger.log("Reading in portmap file %s" %fname)
        with open(fname, "r") as fp:
            d = json.load(fp)
            data['VmLports'].update(d['VmLports'])
            data['VmSegPortPaths'].update(d['VmSegPortPaths'])
            data['VnicSegPortPaths'].update(d['VnicSegPortPaths'])
            
    return data                                

def createNewPortMaps(MC, NSX, segments, portMaps, vms, logger):
    '''
    ports:
       {
          'vm_uuid': {
               'moId': "mo-id",
               'vnics': [
                   {
                      'index': 4000,
                      'data': {}
                      'path': "newpath"
                   },
                   {
                      'index': 4001,
                      'data': {}
                      'path': "newpath1"
                   }
                ]
           }
        }
    '''
    
    ports = {}

    for p in portMaps['VnicSegPortPaths'].keys():
        port={}
        vmId = p.split(':')[0]
        vindex = p.split(':')[1]
        if vmId not in vms.keys():
            logger.log("VM with instanceUUID not found in list of VMs seen by MC" %port['vmId'])
            continue
    
        if vmId in ports.keys():
            port = ports[vmId]
        else:
            ports[vmId] = {}
            port = ports[vmId]
            port['moId'] = vms[vmId]


        vnic={}
        vnic['index'] = vindex
        oldLsp = portMaps['VnicSegPortPaths'][p].split('/')
        oldSeg = "/".join(oldLsp[0:4])
        newSeg = None
        for seg in segments['mappings']:
            if seg['source'] == oldSeg:
                newSeg = seg['destination']
                break
        if not newSeg:
            logger.log("Segment mapping not found for source segment: %s, %s" %(oldSeg, oldLsp))
            continue

        oldPort=MC.list(api="/policy/api/v1%s"%portMaps['VnicSegPortPaths'][p], verbose=False)
        if not oldPort:
            logger.log("Port not found in MC for VM %s %s:%s" %(port['moId'], vmId,vindex))
            return None

        # shouldn't need to do this because they are read only
        oldPort.pop('path')
        oldPort.pop('relative_path')
        if 'realization_id' in oldPort.keys():
            oldPort.pop('realization_id')
        oldPort.pop('parent_path')
        portId = oldPort['unique_id']
        oldPort.pop('unique_id')

        vnic['path'] = "%s/ports/%s" %(newSeg, portId)
        vnic['data'] = oldPort

        if 'vnics' in port.keys():
            port['vnics'].append(vnic)
        else:
            port['vnics'] = [vnic]
        
    return ports
        

def validateSegments(MC, NSX, logger, args):
    logger.log("Opening segment mapping file: %s" % args.segmentMap)
    with open(args.segmentMap, "r") as fp:
        segments = json.load(fp)
        if 'mappings' not in segments.keys():
            logger.log("Invalid segment mapping file")
            return None

    logger.log("Retrieving segments from NSX running MC and Destination NSX...")
    srcSegments=MC.list(api='/policy/api/v1/infra/segments', verbose=False)
    dstSegments=NSX.list(api='/policy/api/v1/infra/segments', verbose=False)
    logger.log("Validating mapped segments")
    for seg in segments['mappings']:
        srcFound=False
        dstFound=False
        seg['source'] = seg['source'].strip()
        seg['destination'] = seg['destination'].strip()
        for s in srcSegments['results']:
            if s['path'] == seg['source']:
                srcFound = True
                break
        if not srcFound:
            logger.log("Segment %s not found on NSX running migration coordinator")
            return None
        for d in dstSegments['results']:
            if d['path'] == seg['destination']:
                dstFound = True
                break
            if not srcFound:
                logger.log("Segment %s not found on destination NSX")
                return None
            
    return segments

def processContextProfiles(MC, NSX, logger, args):
    logger.log("Retrieving list of context profiles created by Migration Coordinator...")
    vCtx = MC.list(api='/policy/api/v1/infra/tags/effective-resources?scope=v_origin&filter_text=PolicyContextProfile', verbose=False)

    dCtx = NSX.list(api='/policy/api/v1/infra/context-profiles', verbose=False)

    ctxApis={}
    ctxApis['resource'] = "PolicyContextProfile"
    ctxApis['data'] = []
    notFound = 0
    for i in vCtx['results']:
        path=i['path']
        if path=="/infra/context-profiles/APP_SVN":
            logger.log("WARN skipping migration of /infra/context-profiles/APP_SVN")
            continue
        if path=="/infra/context-profiles/APP_POP2":
            logger.log("WARN skipping migration of /infra/context-profiles/APP_POP2")
            continue
        found=False
        mcCtx = MC.list(api='/policy/api/v1'+path, verbose=False)
        for d in dCtx['results']:
            if compare_ctx(mcCtx, d, nameCheck=args.serviceNameCheck):
                logger.log("Found source ctx: %s in dest: %s"%(path, d['path']))
                found=True
                break
        if not found:
            logger.log("Migrated service %s not found on destination" %path)
            logger.log(mcCtx, True)
            ctx={}
            ctx['path'], ctx['body'] = transformCtx(mcCtx, args)
            ctx['oldPath'] = mcCtx['path']
            ctxApis['data'].append(ctx)
            notFound+=1
    '''
    slogger = Logger(file="newContextProfilesApi.json", verbose=False)
    slogger.log(ctxApis, jsonData=True, jheader=False)
    slogger.close()
    '''
    return ctxApis

def transformCtx(ctx, args):
    name,path,nId = transformPath(ctx['display_name'], ctx['path'],
                                  ctx['id'], args.prefix, args.updateServiceName)
    newCtx = ctx.copy()
    newCtx.pop('path')
    newCtx.pop('parent_path')
    if 'realization_id' in newCtx.keys():
        newCtx.pop('realization_id')
    newCtx['id'] = nId
    newCtx['display_name'] = name

    return path, newCtx

def compare_ctx(src, dst, nameCheck=False):
    if nameCheck:
        if src['display_name'].lower() != dst['display_name'].lower():
            return False
    if len(src['attributes']) != len(dst['attributes']):
        return False

    for a in src['attributes']:
        found=False
        for d in dst['attributes']:
            if compare_attribute_entry(a, d):
                found=True
                break
        if not found:
            break
    return found

def compare_attribute_entry(src, dst):
    if src['attribute_source'] != dst['attribute_source']:
        return False
    if src['datatype'] != dst['datatype']:
        return False
    if 'isAlgType' in src.keys() and 'isAlgType' in dst.keys():
        if src['isAlgType'] != dst['isAlgType']:
            return False
    elif 'isAlgType' in src.keys() and 'isAlgType' not in dst.keys():
        return False
    elif 'isAlgType' not in src.keys() and 'isAlgType' in dst.keys():
        return False

    if src['key'] != dst['key']:
        return False

    if len(src['value']) != len(dst['value']):
        return False
    
    for v in src['value']:
        found=False
        if v in dst['value']:
            found=True
            continue
    if not found:
        return False

    if 'metadata' in src.keys() and 'metadata' not in dst.keys():
        return False
    elif 'metadata' not in src.keys() and 'metadata' in dst.keys():
        return False
    elif 'metadata' in src.keys() and 'metadata' in dst.keys():
        if len(src['metadata']) != len(dst['metadata']):
            return False
        for kv in src['metadata']:
            found=False
            for dv in dst['metadata']:
                if kv['key'] == dv['key']:
                    if kv['value'] == dv['value']:
                        found=True
                        break
            if not found:
                return False
            
                    
    if 'sub_attributes' in src.keys() and 'sub_attributes' not in dst.keys():
        return False
    elif 'sub_attributes' not in src.keys() and 'sub_attributes' in dst.keys():
        return False
    elif 'sub_attributes' in src.keys() and 'sub_attributes' in dst.keys():
        if len(src['sub_attributes']) != len(dst['sub_attributes']):
            return False
        for kv in src['sub_attributes']:
            found=False
            for dv in dst['sub_attributes']:
                if kv['datatype'] == dv['datatype']:
                    if kv['key'] == dv['key']:
                        if kv['value'] == dv['value']:
                            found=True
                            break
            if not found:
                return False

    return True

def processServices(MC, NSX, logger, args):

    logger.log("Retrieving list of services created by Migration Coordinator...")
    VServices = MC.list(api='/policy/api/v1/infra/tags/effective-resources?scope=v_origin&filter_text=Service', verbose=False)

    logger.log("Retrieving list of all services from destination NSX: %s ..." %args.nsx)
    destServices = NSX.list(api='/policy/api/v1/infra/services', verbose=False)
    
    logger.log("Checking to see if destination NSX already has configuration for migrated service")
    notFound = 0
    serviceApis={}
    serviceApis['resource'] = "Service"
    serviceApis['data'] = []
    for i in VServices['results']:
        path = i['path']
        found=False
        mcService = MC.list(api='/policy/api/v1'+path, verbose=False)
        for d in destServices['results']:
            if compare_service(mcService,d, nameCheck=args.serviceNameCheck):
                logger.log("Found source: %s in dest: %s" %(path,d['path']))
                found=True
                break
        if not found:
            logger.log("Migrated service %s not found on destination" %path)
            logger.log(mcService,True)
            svc={}
            svc['path'], svc['body'] = transformService(mcService, args)
            svc['oldPath'] = mcService['path']
            serviceApis['data'].append(svc)
            notFound+=1
            #print("Not found: %s" %path)
    '''
    slogger = Logger(file="newServicesApi.json", verbose=False)
    slogger.log(serviceApis, jsonData=True, jheader=False)
    slogger.close()
    '''
    return serviceApis

def updatePathExpressions(expression, newExpr):
    conjOp = {}
    conjOp['conjuunction_operator'] = "OR"
    conjOp['resource_type'] = "ConjunctionOperator"
    found=False
    if len(newExpr['paths']) == 0:
        return expression
    
    for e in expression:
        if e['resource_type'] == 'PathExpression':
            found = True
            e['paths'].extend(newExpr['paths'])
            break
    if not found:
        if len(expression) > 0:
            expression.append(conjOp)
            expression.append(newExpr)
        else:
            expression.append(newExpr)

    return expression
    
            
        
        
    
def updateGroupPaths(groups, logger, args):
    prefix=args.prefix
    logger.log("Updating all groups names, ids and paths with prefix: %s" %prefix)
    for g in groups:
        if 'url' in g:
            comps = g['url'].split('/')
            subPath = "/".join(comps[:-1])
            newPid="%s%s" %(prefix, comps[-1])
            g['newUrl'] = "%s/%s" %(subPath, newPid)
            g['api']['newUrl'] = g['newUrl']
            g['api']['body']['id'] = newPid
            g['api']['body']['display_name']  = "%s%s" %(prefix, g['api']['body']['display_name'])

            if 'temp_apis' in g:
                g['new_temp_paths'] = []
                g['new_internal_paths_to_delete'] = []
                for tg in g['temp_apis']:
                    comps = tg['url'].split('/')
                    subPath="/".join(comps[:-1])
                    newPid = "%s%s" %(prefix, comps[-1])
                    tg['newUrl'] = "%s/%s" %(subPath, newPid)
                    tg['body']['id'] = newPid
                    tg['body']['display_name'] = "%s%s" %(prefix, tg['body']['display_name'])
                    g['new_temp_paths'].append(tg['newUrl'])
                    g['new_internal_paths_to_delete'].append(tg['newUrl'])
                    if 'expression' not in g['api']['body']:
                        continue
                    for expr in g['api']['body']['expression']:
                        if expr['resource_type'] != "PathExpression":
                            continue
                        for i in range(len(expr['paths'])):
                            if expr['paths'][i] == tg['url']:
                                expr['paths'][i] = tg['newUrl']
                    if 'expression' not in tg['body']:
                        continue

    for g in groups:
        if 'expression' not in g['api']['body']:
            continue
        for e in g['api']['body']['expression']:
            if e['resource_type'] == 'PathExpression':
                for i in range(len(e['paths'])):
                    if '/infra/domains/default/groups' not in e['paths'][i]:
                        continue
                    for gg in groups:
                        if e['paths'][i] == gg['url']:
                            e['paths'][i] = gg['newUrl']
                            
    return groups
                       
                                                         
def processGroups(MC, NSX, logger, args):
    logger.log("Retrieving list of Groups created by Migration Coordinator...")
    vGroups = MC.list(api='/policy/api/v1/infra/tags/effective-resources?scope=v_origin&filter_text=Group', verbose=False)
    logger.log("Retrieving list of temporary groups created by Migration Coordinator...")
    tmpGroups = MC.list(api='/policy/api/v1/infra/tags/effective-resources?scope=v_temporary&filter_text=Group', verbose=False)
    logger.log("Retrieving list of all Groups from destination NSX: %s ..." %args.nsx)
    destServices = NSX.list(api='/policy/api/v1/infra/domains/default/groups', verbose=False)


    logger.log("Reading in storage.json file: %s" %args.storageJson)
    try:
        storageJson = open(args.storageJson, "r")
    except:
        logger.log("Failed to open storage.json file from MC: %s" %args.storageJson)
        return None
    stJ = json.load(storageJson)
    if 'policy_group_runtime_mappings' not in stJ.keys():
        logger.log("No policy gorup runtime mappings found in storage.json")
        groupMappings=[]
    else:
        groupMappings=stJ['policy_group_runtime_mappings']


    # Read and validate the list of user provided segment mappings
    segments = validateSegments(MC, NSX, logger, args)
    if not segments:
        return None

    # Read in and merge all port-mappings created by the pre-migrate API
    portMaps = readPortMappings(logger, args)

    # create new ports from portMaps
    portsApi = createNewPortMaps(MC, NSX, segments, portMaps,
                              stJ['vm_xlate_mappings']['vm_instance_id_moid_mappings'], logger)
    '''
    slogger = Logger(file="newPortsApi.json", verbose=False)
    slogger.log(portsApi, jsonData=True, jheader=False)
    slogger.close()
    '''
    ports = portsApi
    # These cover only groups that MC created with temp ipsets
    logger.log("Updating groups with VM and vNIC static memberships")
    for g in groupMappings:
        if 'VirtualMachine' in g.keys():
            vmExpr = {}
            vmExpr['resource_type'] = 'PathExpression'
            vmExpr['paths'] = []
            for vm in g['VirtualMachine']:
                if vm not in ports.keys():
                    logger.log("VM %s not found in ports list!!!" %vm)
                    return None
                for i in ports[vm]['vnics']:
                    vmExpr['paths'].append(i['path'])
            g['api']['body']['expression'] = updatePathExpressions(g['api']['body']['expression'],
                                                                   vmExpr)
        if 'VirtualNetworkInterface' in g.keys():
            vmExpr = {}
            vmExpr['resource_type'] = 'PathExpression'
            vmExpr['paths'] = []
            for vn in g['VirtualNetworkInterface']:
                vmId = "-".join(vn.split('-')[:-1])
                vIndex = vn.split('-')[-1]
                if vmId not in ports.keys():
                    logger.log("VM %s not found in ports list!!!" %vmId)
                    return None
                for i in ports[vmId]['vnics']:
                    if i['index'] == vIndex:
                        vmExpr['paths'].append(i['path'])
            data=g['api']['body']
            data['expression'] = updatePathExpressions(data['expression'], vmExpr)
            
    # there are groups created by MC that that are not covered in storage.json
    # like ipset based groups that don't need temp ipsets
    logger.log("Iterating through all groups created and realized by MC")
    for g in vGroups['results']:
        foundGM = False
        for gm in groupMappings:
            if g['path'] == gm['url']:
                # this group is already covered in group mappings
                foundGM=True
                continue

        if not foundGM:
            logger.log("Group %s not found in storage.json, reading from MC and adding to mappings" %g['path'])
            newData=MC.list(api="%s%s" % ("/policy/api/v1",g['path']), verbose=False)
            newGM ={}
            newGM['url'] = g['path']
            newGM['api'] = {}
            newGM['api']['url'] = g['path']
            newGM['api']['body'] = newData.copy()
            logger.log(newGM['api']['body'], jsonData=True, jheader=False)
            newGM['api']['body'].pop('path')
            newGM['api']['body'].pop('parent_path')
            if 'realization_id' in newGM['api']['body'].keys():
                newGM['api']['body'].pop('realization_id')
            newGM['api']['method_name'] = "PATCH"
            #groupMappings.append(newGM)
            groupMappings[:0] = [newGM]
            
    # fill in tmp apply-to groups
    logger.log("Updating temporary applied-to groups with their port or VM memberships")
    for g in groupMappings:
        if 'is_applied' not in g.keys() or not g['is_applied']:
            continue
        if 'AppliedToVirtualNetworkInterface' not in g.keys():
            logger.log("WARN No Apply-to VIFs block in apply-to group %s" % g['url'])
            if 'AppliedToVmMOID' not in g.keys():
                logger.log("WARN No Apply-to VMs block in applly-to group %s" % g['url'])
                continue

        '''
        if len(g['AppliedToVirtualNetworkInterface']) == 0:
            continue
        '''
        
        applyToP = None
        for p in g['temp_paths']:
            if 'AppliedTo' in p:
                applyToP = p
                break
        if not applyToP:
            logger.log("WARN No temp applied-to path for %s" %g['url'])
            continue

        applyToG = None
        for t in g['temp_apis']:
            if t['url'] == applyToP:
                applyToG = t
                break
        if not applyToG:
            logger.log("WARN No temp apply-to group for temp group %s" %applyToP)
            continue

        vmExpr={}
        vmExpr['resource_type'] = 'PathExpression'
        vmExpr['paths'] = []

        if 'AppliedToVirtualNetworkInterface' in g.keys():
            for v in g['AppliedToVirtualNetworkInterface']:
                vmId = "-".join(v.split('-')[:-1])
                vIndex = v.split('-')[-1]
                if vmId not in ports.keys():
                    logger.log("WARN VM %s not found in ports list!!!" %vmId)
                    return None
                for i in ports[vmId]['vnics']:
                    if i['index'] == vIndex:
                        vmExpr['paths'].append(i['path'])
            data=applyToG['body']
            logger.log("Updating group %s with apply-to vms VIFs" %applyToG['url'])
            data['expression'] = updatePathExpressions(data['expression'], vmExpr)
            logger.log(applyToG, jsonData=True)

        if 'AppliedToVmMOID' in g.keys():
            if 'AppliedToVirtualNetworkInterface' in g.keys():
                continue
            logger.log("Group %s has VM applied-to, but not vifs" %g['url'])
            # get all ports for the VM
            vmExpr={}
            vmExpr['resource_type'] = 'PathExpression'
            vmExpr['paths'] = []
            for vm in g['AppliedToVmMOID']:
                found=False
                for p in ports.keys():
                    if ports[p]['moId'] == vm:
                        for n in ports[p]['vnics']:
                            vmExpr['paths'].append(n['path'])
                        found = True
                        break
                if not found:
                    logger.log("WARN Group %s has apply to VM %s that doesn't exist in portlist created by pre_migrate" % (g['url'], vm))
                    return None
            data=applyToG['body']
            logger.log("Updating group %s with apply-to vms" %applyToG['url'])
            data['expression'] = updatePathExpressions(data['expression'], vmExpr)
    
    # fix segment memberships to new map
    logger.log("Updating segment mappings in groups")
    for g in groupMappings:
        #logger.log(g, jsonData=True)
        if 'expression' not in g['api']['body']:
            continue
        for e in  g['api']['body']['expression']:
            if e['resource_type'] == 'PathExpression':
                paths = e['paths']
                for i in range(len(paths)):
                    if '/infra/segments/' not in paths[i]:
                        continue
                    if '/ports/' in paths[i]:
                        continue
                    found=False
                    for s in segments['mappings']:
                        if s['source'] == paths[i]:
                            logger.log("Replacing segment %s with mapped segment %s in group %s"
                                       %(paths[i], s['destination'], g['url']))
                            paths[i] = s['destination']
                            found=True
                            break
                    if not found:
                        logger.log("Segment mapping not found for %s in group %s" %
                                   (paths[i], g['url']))
                        return None
                    
        if 'temp_apis' not in g.keys():
            continue
        for tg in g['temp_apis']:
            if 'expression' not in tg['body']:
                continue
            for e in  tg['body']['expression']:
                if e['resource_type'] == 'PathExpression':
                    paths = e['paths']
                    for i in range(len(paths)):
                        if '/infra/segments/' not in paths[i]:
                            continue
                        if '/ports/' in paths[i]:
                            continue
                        found=False
                        for s in segments['mappings']:
                            if s['source'] == paths[i]:
                                logger.log("Replacing segment %s with mapped segment %s in group %s"
                                           %(paths[i], s['destination'], g['url']))
                                paths[i] = s['destination']
                                found=True
                                break
                            if not found:
                                logger.log("Segment mapping not found for %s in group %s" %
                                       (paths[i]), g['url'])
                                return None
            
    # Groups with VM memberships now have port memberships
    # fix paths
    groupMappings=updateGroupPaths(groupMappings, logger, args)
    output={}
    output['groupMappings'] = groupMappings
    output['ports'] = portsApi

    '''
    slogger = Logger(file="newGroupsApi.json", verbose=False)
    slogger.log(output, jsonData=True, jheader=False)
    slogger.close()
    '''
    return output

def findNewGroup(group, grouplist):
    if group == "ANY":
        return group
    for g in grouplist:
        if g['url'] == group:
            return g['newUrl']
    return None

def findNewService(service, servicelist):
    if service == "ANY":
        return service
    for s in servicelist:
        if s['oldPath'] == service:
            return s['path']
    return None
def findNewProfile(profile, profilelist):
    if profile == "ANY":
        return profile
    for s in profilelist:
        if s['oldPath'] == profile:
            return s['path']
    return None

def processPolicies(MC, NSX, services, contexts, groups, logger, args):
    logger.log("Retrieving list of policies created by MC")
    mcPolicies = MC.list(api='/policy/api/v1/infra/tags/effective-resources?scope=v_origin&filter_text=SecurityPolicy', verbose=False)

    policiesApi = {}
    policiesApi['resources']='SecurityPolicy'
    policiesApi['data'] = []
    for mcp in mcPolicies['results']:
        p = MC.list(api="/policy/api/v1%s" %mcp['path'], verbose=False)
        logger.log("Updating policy %s" %p['path'])
        policyName, policyPath, policyId = transformPath(p['display_name'],
                                                         p['path'],
                                                         p['id'],
                                                         args.prefix,
                                                         change=True)
        logger.log("Updating policy %s to %s" %(p['path'], policyPath))
        data={}
    
        policy=p.copy()
        policy['id'] = policyId
        policy['display_name'] = policyName
        policy.pop('path')
        policy.pop('parent_path')
        if 'realization_id' in policy.keys():
            policy.pop('realization_id')
        if 'target_type' in policy.keys():
            policy.pop('target_type')
        data['oldPath'] = p['path']
        data['path'] = policyPath
        data['body'] = policy
        for r in policy['rules']:
            r['id'] = "%s%s" %(args.prefix, r['id'])
            r.pop('path')
            r.pop('parent_path')
            if 'realization_id' in r.keys():
                r.pop('realization_id')
            r['display_name'] = "%s%s" %(args.prefix, r['display_name'])
            for i in range(len(r['source_groups'])):
                ngrp = findNewGroup(r['source_groups'][i], groups)
                if not ngrp:
                    logger.log("WARN Policy %s - can't find group %s for rule source"
                               %(p['path'], r['source_groups'][i]))
                    return None
                else:
                    r['source_groups'][i] = ngrp
            for i in range(len(r['destination_groups'])):
                ngrp = findNewGroup(r['destination_groups'][i], groups)
                if not ngrp:
                    logger.log("WARN Policy %s - can't find group %s for rule destination"
                               %(p['path'], r['destination_groups'][i]))
                    return None
                else:
                    r['destination_groups'][i] = ngrp
            for i in range(len(r['scope'])):
                ngrp = findNewGroup(r['scope'][i], groups)
                if not ngrp:
                    logger.log("WARN Policy %s - can't find group %s for rule scope"
                               %(p['path'], r['scope'][i]))
                    return None
                else:
                    r['scope'][i] = ngrp


            for i in range(len(r['services'])):
                nsvc = findNewService(r['services'][i], services)
                if not nsvc:
                    logger.log("Policy %s - can't find migrated service %s for rule services...checking destination for pre-existing services"
                               %(p['path'], r['services'][i]))
                    found = False
                    attempts = 1
                    while attempts < 10:
                        dsvc = NSX.list(api="/policy/api/v1%s" %r['services'][i], verbose=False)
                        if 'error_code' in dsvc.keys():
                            logger.log("WARN Policy %s uses a service %s in rule that doesn't exist.  Attempt %d of 10" 
                                       %(p['path'], r['services'][i], attempt), verbse=True)
                            if attemt != 10:
                                logger.log("WARN Sleeping 10 seconds for next attempt to find group realization")
                                time.sleep(10)
                                continue
                            else:
                                return None
                        else:
                            logger.log("Policy %s - pre-existing service %s found"
                                       %(p['path'], r['services'][i]))
                            found = True
                            break
                else:
                    r['services'][i] = nsvc

            for i in range(len(r['profiles'])):
                nsvc = findNewProfile(r['profiles'][i], contexts)
                if not nsvc:
                    logger.log("Policy %s - can't find migrated context profile  %s for rule ctx...checking destination for pre-existing ctx profiles"
                               %(p['path'], r['profiles'][i]))
                    found=False
                    attempts = 1
                    while attempts < 10:
                        dsvc = NSX.list(api="/policy/api/v1%s" %r['profiles'][i], verbose=False)
                        if 'error_code' in dsvc.keys():
                            logger.log("WARN Policy %s uses a ctx profile %s in rule that doesn't exist, attempt %d of 10"
                                       %(p['path'], r['profiles'][i], attempt))
                        
                            return None
                    else:
                        logger.log("Policy %s - pre-existing ctx profile %s found"
                                   %(p['path'], r['profiles'][i]))
                else:
                    r['profiles'][i] = nsvc
        policiesApi['data'].append(data)
    
    '''
    slogger = Logger(file="newPoliciesApi.json", verbose=False)
    slogger.log(policiesApi, jsonData=True, jheader=False)
    slogger.close()
    '''
    return policiesApi                    

def reUpdateMigrationLog(data, filename):
    slogger=Logger(file=filename, mode="w", verbose=False)
    slogger.log(data, jsonData=True, jheader=False)
    slogger.close()
    
def main():
    args = parseParameters()
    site="default"
    enforcementPoint="default"
    domain="default"

    logger = Logger(file=args.logfile, verbose=False)
    
    if not args.mcPassword:
        mcPassword = getpass.getpass("Enter the password for %s and user %s"
                                     %(args.mc, args.mcUser))
    else:
        mcPassword=args.mcPassword

    if not args.nsxPassword:
        nsxPassword = getpass.getpass("Enter the password for %s and user %s"
                                     %(args.nsx, args.nsxUser))
    else:
        nsxPassword=args.nsxPassword
    
                                
        
    mc = connections.NsxConnect(server=args.mc, logger=logger,
                                user=args.mcUser,
                                password=mcPassword,
                                cookie=None, cert=None,
                                global_infra=False, global_gm=False,
                                site=site,
                                enforcement=enforcementPoint,
                                domain=domain,
                                timeout=None)
    MC = NSXT(mp=mc, logger=logger,site=site, enforcementPoint=enforcementPoint)
    logger.log("Connected to %s with user %s" % (args.mc, args.mcUser), verbose=True)
    nsx = connections.NsxConnect(server=args.nsx, logger=logger,
                                 user=args.nsxUser,
                                 password=nsxPassword,
                                 cookie=None, cert=None,
                                 global_infra=False, global_gm=False,
                                 site=site,
                                 enforcement=enforcementPoint,
                                 domain=domain,
                                 timeout=None)

    NSX = NSXT(mp=nsx, logger=logger, site=site, enforcementPoint=enforcementPoint)
    logger.log("Connected to %s with user %s" % (args.nsx, args.nsxUser), verbose=True)

    logger.log("Retrieving list of services created by Migration Coordinator...", verbose=True)
    VServices = MC.list(api='/policy/api/v1/infra/tags/effective-resources?scope=v_origin&filter_text=Service', verbose=False)

    logger.log("Retrieving list of all services from destination NSX: %s ..." %args.nsx, verbose=True)
    destServices = NSX.list(api='/policy/api/v1/infra/services', verbose=False)


    migrationData={}
    
    logger.log("Processing services", verbose=True)
    serviceApis=processServices(MC, NSX, logger, args)
    migrationData['services'] = serviceApis
    
    logger.log("Processing context profiles", verbose=True)
    ctxApis = processContextProfiles(MC, NSX, logger, args)
    migrationData['contexts'] = ctxApis
    
    logger.log("Processing ports and groups", verbose=True)
    groupMappings=processGroups(MC, NSX, logger, args)
    ports = groupMappings['ports']
    migrationData['groups'] = groupMappings['groupMappings']
    migrationData['ports'] = ports
    
    
    logger.log("Processing Security Policies", verbose=True)
    policyApis = processPolicies(MC, NSX, serviceApis['data'],
                               ctxApis['data'], groupMappings['groupMappings'],
                               logger, args)

    if not policyApis:
        logger.log("ERROR - policy")
        system.exit()
    migrationData['policies'] = policyApis

    # order of creation: services->ctx profiles->ports->groups->policies
    failedApis = {}
    failedApis['resource'] = 'Service'
    failedApis['data'] = []
    logger.log("Submitting services configurations to destination", verbose=True)
    for api in serviceApis['data']:
        api['migrate'] = {}
        url = "/policy/api/v1" + api['path']
        r = NSX.submitApi(url, api['body'], logger, args)
        if r['status_code'] != 200:
            logger.log("ERROR - Submission of Service %s did not succeed" %api['path'])
            api['migrate']['successful'] = False
            failedApis['data'].append(api)
        else:
            api['migrate']['successful'] = True
        api['migrate']['apiResult'] = r


    if len(failedApis['data']) > 0:
        logger.log("ERROR: Failure to submit %d service APIs" % len(failedApis['data']),
                   verbose=True)
        sys.exit()

    
    failedApis = {}
    failedApis['resource'] = 'PolicyContextProfile'
    failedApis['data'] = []
    logger.log("Submitting Context Profile configurations to destination", verbose=True)
    for api in ctxApis['data']:
        api['migrate'] = {}
        url = "/policy/api/v1" + api['path']
        r = NSX.submitApi(url, api['body'], logger, args)
        if r['status_code'] != 200:
            logger.log("ERROR - submission for Context Profile %s did not succeed" %api['path'],
                       verbose=True)
            api['migrate']['successful'] = False
            failedApis['data'].append(api)
        else:
            api['migrate']['successful'] = True
            
        api['migrate']['apiResult'] = r
    ctxApis['failedSubmissions'] = failedApis
    reUpdateMigrationLog(migrationData, args.migrationData)

    if len(failedApis['data']) > 0:
        logger.log("ERROR: Failure to submit %d Context Profile APIs" % len(failedApis['data']),
                   verbose=True)
        sys.exit()
        
    failedApis = {}
    failedApis['resource'] = 'SegmentPort'
    failedApis['data'] = []
    logger.log("Submitting SegmentPort configurations to destination", verbose=True)
    for api in ports:
        port = ports[api]
        for v in port['vnics']:
            v['migrate'] = {}
            url = "/policy/api/v1" + v['path']
            r = NSX.submitApi(url, v['data'], logger, args)

            if r['status_code'] != 200:
                logger.log("ERROR - submission for port %s did not succeed" %api['path'],
                           verbose=True)
                v['migrate']['successful'] = False
                failedApis['data'].append(api)
            else:
                v['migrate']['successful'] = True
            v['migrate']['apiResult'] = r
    reUpdateMigrationLog(migrationData, args.migrationData)

    ports['failedSubmissions'] = failedApis
    if len(failedApis['data']) > 0:
        logger.log("ERROR: Failure to submit %d SegmentPort APIs" % len(failedApis['data']),
                   verbose=True)
        sys.exit()

    failedApis = {}
    failedApis['resource'] = 'Group'
    failedApis['data'] = []
    # must create temp APIs before main one
    logger.log("Submitting Group configurations to destination", verbose=True)
    for gm in groupMappings['groupMappings']:
        gm['migrate'] = {}
        if 'temp_apis' in gm.keys():
            gm['migrate']['temp_apis'] = []
            for tg in gm['temp_apis']:
                tgResult={}
                url = "/policy/api/v1" + tg['newUrl']
                r = NSX.submitApi(url, tg['body'], logger, args)
                if r['status_code'] != 200:
                    logger("ERROR - submission for group %s temp_api %s did not succeed"
                           %(gm['newUrl'], tg))
                    tgResult['successful'] = False
                    failedApis['data'].append(api)
                else:
                    tgResult['successful'] = True
                tgResult['apiResult'] = r
                gm['migrate']['temp_apis'].append(tgResult)
                    
        if 'api' in gm.keys():
            gm['migrate']['api'] = {}
            url = "/policy/api/v1" + gm['api']['newUrl']
            r = NSX.submitApi( url, gm['api']['body'], logger, args)
            if r['status_code'] != 200:
                logger.log("ERROR - submission for group %s did not succeed" %gm['api']['newUrl'])
                gm['migrate']['api']['successful'] = False
                failedApis['data'].append(gm['api'])
            else:
                gm['migrate']['api']['successful'] = True
            gm['migrate']['api']['apiResult'] = r
    reUpdateMigrationLog(migrationData, args.migrationData)


    if len(failedApis['data']) > 0:
        logger.log("ERROR: Failure to submit %d Group APIs" % len(failedApis['data']),
                   verbose=True)
        sys.exit()
                
        
    failedApis = {}
    failedApis['resource'] = 'SecurityPolicy'
    failedApis['data'] = []
    logger.log("Submitting Security Policy configurations to destination", verbose=True)
    for api in policyApis['data']:
        api['migrate'] = {}
        url = "/policy/api/v1" + api['path']
        r = NSX.submitApi(url, api['body'], logger, args)
        if r['status_code'] != 200:
            logger.log("ERROR - submission for SecurityPolicy %s did not succeed" %api['path'])
            failedApis['data'] = append(api)
            api['migrate']['successful'] = False
        else:
            api['migrate']['successsful'] = True
        api['migrate']['apiResult'] = r
    reUpdateMigrationLog(migrationData, args.migrationData)

    if len(failedApis['data']) > 0:
        logger.log("ERROR: Failure to submit %d Security Policy APIs" % len(failedApis['data']),
                   verbose=True)
        sys.exit()

def transformPath(name, path, Oid, prefix, change=True):
    if change:
        pcom = path.split('/')
        newPath="/".join(pcom[:-1])
        newPath="%s/%s%s" %(newPath,prefix,pcom[-1])
        nId="%s%s" %(prefix,Oid)
        newName="%s%s" %(prefix, name)
    else:
        newName = name
        nId = Oid
        newPath = path
    return newName,newPath,nId


def addTag(data, prefix):
    tag={}
    tag['scope']='v_origin_site'
    tag['tag'] = prefix

    if 'tags' in data.keys():
        data['tags'].append(tag)
    else:
        data['tags'] = [tag]

    return data

    
def transformService(svc, args):
    name,path,nId = transformPath(svc['display_name'], svc['path'],
                                  svc['id'], args.prefix,
                                  args.updateServiceName)
    newSvc=svc.copy()
    newSvc.pop('path')
    newSvc.pop('parent_path')
    if 'realization_id' in newSvc.keys():
        newSvc.pop('realization_id')
    newSvc['id'] = nId
    newSvc['display_name'] = name

    for s in newSvc['service_entries']:
        s.pop('path')
        s.pop('parent_path')
        if 'realization_id' in s.keys():
            s.pop('realization_id')
        if args.updateServiceName:
            s['id'] = "%s%s" %(args.prefix,s['id'])
    return path,newSvc


def compare_service(src, dst, nameCheck=False):
    if src['service_type'] != dst['service_type']:
        return False
    if nameCheck:
        if src['display_name'].lower() != dst['display_name'].lower():
            return False

    if len(src['service_entries']) != len(dst['service_entries']):
        return False

    for srcE in src['service_entries']:
        found=False
        for dstE in dst['service_entries']:
            if compare_service_entry(srcE, dstE, nameCheck=True):
                found=True
                break
        if not found:
            break
    return found
        
'''
Compare two NSX-T service entries.
Return True if they have the same configuration.
Return False if they do not have the same configuration
Name checks are case insensitive
'''
def compare_service_entry(srcEntry, dstEntry, nameCheck=False):
    
    if srcEntry['resource_type'] != dstEntry['resource_type']:
        return False

    if nameCheck:
        if srcEntry['display_name'].lower() != dstEntry['display_name'].lower():
            return False

    if srcEntry['resource_type'] == 'L4PortSetServiceEntry':
        if srcEntry['l4_protocol'] != dstEntry['l4_protocol']:
            return False
        c = [x for x in srcEntry['source_ports'] + dstEntry['source_ports'] if x not in srcEntry['source_ports'] or x not in  dstEntry['source_ports']]
        if c:
            return False

        c = [x for x in srcEntry['destination_ports'] + dstEntry['destination_ports'] if x not in srcEntry['destination_ports'] or x not in  dstEntry['destination_ports']]
        if c:
            return False

    elif srcEntry['resource_type'] == 'ALGTypeServiceEntry':
        if srcEntry['alg'] != dstEntry['alg']:
            return False
        
        c = [x for x in srcEntry['source_ports'] + dstEntry['source_ports'] if x not in srcEntry['source_ports'] or x not in  dstEntry['source_ports']]
        if c:
            return False

        c = [x for x in srcEntry['destination_ports'] + dstEntry['destination_ports'] if x not in srcEntry['destination_ports'] or x not in  dstEntry['destination_ports']]
        if c:
            return False
        
    elif srcEntry['resource_type'] == 'EtherTypeServiceEntry':
        if srcEntry['ether_type'] != dstEntry['ether_type']:
            return False

    elif srcEntry['resource_type'] == 'ICMPTypeServiceEntry':
        if srcEntry['protocol'] != dstEntry['protocol']:
            return False
        if 'icmp_type' in srcEntry.keys() and 'icmp_type' not in dstEntry.keys():
            return False
        if 'icmp_type' not in srcEntry.keys() and 'icmp_type' in dstEntry.keys():
            return False
        if 'icmp_type' in srcEntry.keys() and 'icmp_type' in dstEntry.keys():
            if srcEntry['icmp_type'] != dstEntry['icmp_type']:
                return False
        if 'icmp_code' in srcEntry.keys() and 'icmp_code' not in dstEntry.keys():
            return False
        if 'icmp_code' not in srcEntry.keys() and 'icmp_code' in dstEntry.keys():
            return False
        if 'icmp_code' in srcEntry.keys() and 'icmp_code' in dstEntry.keys():
            if srcEntry['icmp_code'] != dstEntry['icmp_code']:
                return False
            
    elif srcEntry['resource_type'] == 'IGMPTypeServiceEntry':
        # nothing to do there
        pass
    elif srcEntry['resource_type'] == 'IPProtocolServiceEntry':
        if srcEntry['protocol_number'] != dstEntry['protocol_number']:
            return False
    elif srcEntry['resource_type'] == 'NestedServiceServiceEntry':
        # this is incorrect way of checking...so should always fail
        if srcEntry['nested_service_path'] != destEntry['nested_service_path']:
            return False
            
            
    return True
    
    
if __name__=="__main__":
    main()
    
