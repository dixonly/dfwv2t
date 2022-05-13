#!/usr/bin/env python3
import sys
import connections
import argparse
import getpass
import json
import datetime
from migrator import Logger, NSXT

def parseParameters():
    parser=argparse.ArgumentParser()
    parser.add_argument("--nsx", required=True,
                        help="IP or FQDN of the destination NSX Manager")
    parser.add_argument("--nsxUser", required=False,
                        default="admin",
                        help="User name to connect to destination NSX Manger")
    parser.add_argument("--nsxPassword", required=False,
                        help="Password for nsxUser")
    parser.add_argument("--groupsJson", required=True,
                        help="The newGroupsApi.json file produced by migrator.py")
    parser.add_argument("--prefix", required=True,
                        help="The prefix used for migrator.py")
    parser.add_argument("--logfile", required=False,
                        default="postmigrate-log.txt",
                        help="The prefix used for migrator.py")
    
    
    args = parser.parse_args()
    return args

def addPostMigrateData(mapping, entry, group, update):
    entry['postMigrate'] = {}
    entry['postMigrate']['body'] = group
    entry['postMigrate']['url'] = group['path']
    entry['postMigrate']['update'] = update
    mapping.append(entry)
        
def fixExpressions(group):
    if len(group['expression']) == 0:
        return

    for e in group['expression'][:]:
        if e['resource_type'] == "PathExpression":
            if len(e['paths']) == 0:
                group['expression'].remove(e)

    con = True
    for e in group['expression'][:]:
        if e['resource_type'] == 'ConjunctionOperator':
            if con:
                group['expression'].remove(e)
            else:
                con=False
    
def processGroups(NSX, groupMaps, groups, logger, args):
    postMaps={}
    postMaps['groupMappings'] = []
    postMap = postMaps['groupMappings']
    
    for gm in groupMaps['groupMappings']:
        deleteGroups=[]
        logger.log("Checking group %s for temp groups" %gm['newUrl'], verbose=True)
        primaryGroup = NSX.list(api='/policy/api/v1'+gm['newUrl'], verbose=False)
        
        if 'new_internal_paths_to_delete' not in gm.keys():
            logger.log("Group %s does not have any temporary groups for clean up" % gm['newUrl'], False)
            addPostMigrateData(postMap, gm, primaryGroup, False)
            continue

        if len(gm['new_internal_paths_to_delete']) != len(gm['temp_apis']):
            logger.log("Group %s paths to delete doesn't equal # of temp apis" % gm['newUrl'], verbose=True)
        if not 'expression' in primaryGroup:
            logger.log("WARN - Group has %d temporary groups to clean up, but it doesn't have any membership expressions" %(gm['newUrl'], len(gm['new_internal_paths_to_delete'])))
            addPostMigrateData(postMap, gm, primaryGroup, False, gm['new_internal_paths_to_delete'])
            continue

        for dg in gm['new_internal_paths_to_delete']:
            found=False
            for g in groups:
                if g['path'] == dg:
                    found=True
                    deleteGroups.append(dg)
                    break
            if not found:
                logger.log("Temporary group %s not found on NSX: %s"
                           %(dg, args.nsx), verbose=False)
            else:
                logger.log("Group %s has to delete temp nested group %s"
                           %(gm['newUrl'], dg), verbose=False)
            found=False
            for e in primaryGroup['expression']:
                if e['resource_type'] == 'PathExpression':
                    for i in range(len(e['paths'])):
                        if e['paths'][i] == dg:
                            logger.log("Adding removal of  %s from group %s expressions"
                                       %(dg, primaryGroup['path']), verbose=True)
                            e['paths'].remove(dg)
                            found=True
                            break
                if found:
                    break
            fixExpressions(primaryGroup)
            if not found:
                logger.log("Group %s has temporary path %s that's not found in its expressions"
                           %(primaryGroup['path'], dg), verbose=True)

        logger.log("Updated group %s content: " %primaryGroup['path'], verbose=False)
        logger.log(primaryGroup, jsonData=True, jheader=True, verbose=False)
        addPostMigrateData(postMap, gm, primaryGroup, True)

    slogger = Logger(file="postMigrateGroup.json", verbose=False)
    slogger.log(postMaps, jsonData=True, jheader=False)
    slogger.close()

    return postMaps

def submitGroups(NSX, postMaps, logger, args):
    for gm in postMaps['groupMappings']:
        if 'postMigrate' not in gm:
            logger.log("WARN - Group %s does not have any post migration data" % gm['newUrl'],
                       verbose=True)
            continue
        
        g = gm['postMigrate']
        g['status'] = {}
        g['status']['groupUpdate'] = []
        g['status']['deletions'] = []
        if not g['update']:
            logger.log("Group %s does not need post-migration cleanup" % g['url'])
        else:
            api='/policy/api/v1' + g['url']
            r = submitApi(NSX, api, g['body'], logger, args)
            if r['status_code'] != 200:
                logger.log("ERROR  - change for group %s did not succeeed" %g['url'], verbose=True)
                g['status']['successful'] = False
            else:
                logger.log("Post migrate membership cleanup for %s succeeded" %g['url'])
                g['status']['successful'] = True
                g['status']['groupUpdate'].append(r)

            
        if 'new_internal_paths_to_delete' not in gm.keys() \
           or len(gm['new_internal_paths_to_delete']) == 0:
            logger.log("Group %s has not temp groups to delete" % gm['newUrl'])
            
        else:
            for dg in gm['new_internal_paths_to_delete']:
                tg = NSX.mp.get(api="/policy/api/v1" + dg, verbose=False)
                if 'error_code' in tg.keys():
                    logger.log("Temporary group %s not found for deletion" %dg)
                else:
                    logger.log("Deleting temporary group %s" %dg)
                    NSX.mp.delete(api='/policy/api/v1'+ dg, verbose=True)
                    g['status']['deletions'].append(dg)
        
    slogger = Logger(file="postMigrateGroupResults.json", verbose=False)
    slogger.log(postMaps, jsonData=True, jheader=False)
    slogger.close()
    
    
def main():
    args = parseParameters()
    site="default"
    enforcementPoint="default"
    domain="default"

    logger = Logger(file=args.logfile, verbose=False)
    
    if not args.nsxPassword:
        nsxPassword = getpass.getpass("Enter the password for %s and user %s"
                                     %(args.nsx, args.nsxUser))
    else:
        nsxPassword=args.nsxPassword
    
                                
        
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

    logger.log("Retrieving group configs from %s" %args.groupsJson, verbose=True)
    with open(args.groupsJson, "r") as fp:
        groupMaps = json.load(fp)

    logger.log("Number of groups found in newGroups.json: %d" %len(groupMaps['groupMappings']), verbose=True)
    migratedGroups = NSX.list(api='/policy/api/v1/infra/tags/effective-resources?scope=v_origin_site&tag=%s&filter_text=Group' % args.prefix, verbose=False)
    if migratedGroups['result_count'] == 0:
        logger.log("No groups found on NSX Manager %s that were migrated with prefix %s"
                   %(args.nsx, args.prefix), verbose=True)
    else:
        logger.log("Processing %d groups on NSX Manger %s that were migrated with prefix %s"
                   %(migratedGroups['result_count'], args.nsx, args.prefix), verbose=True)

    postMaps = processGroups(NSX, groupMaps,
                         migratedGroups['results'],
                         logger, args)

    logger.log("Submitting changes to NSX: %s" %args.nsx, verbose=True)
    data = submitGroups(NSX, postMaps, logger, args)
    
def submitApi(NSX, api, data, logger, args):
    req = {}
    req['method'] = "PATCH"
    req['api'] = api
    r = NSX.mp.patch(api=api,data=data,verbose=True, trial=False)
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
    
    
if __name__=="__main__":
    main()
    
