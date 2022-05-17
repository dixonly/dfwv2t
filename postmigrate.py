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
    parser.add_argument("--migrationData", required=True,
                        help="The migration data JSON  file produced by migrator.py")
    parser.add_argument("--postData", required=True,
                        help="File to store post migration auditing data")
    parser.add_argument("--prefix", required=True,
                        help="The prefix used for migrator.py")
    parser.add_argument("--logfile", required=False,
                        default="postmigrate-log.txt",
                        help="The prefix used for migrator.py")
    
    
    args = parser.parse_args()
    return args

def addPostMigrateData(entry, group, update):
    entry['postMigrate'] = {}
    entry['postMigrate']['body'] = group
    entry['postMigrate']['url'] = group['path']
    entry['postMigrate']['update'] = update
        
def fixExpressions(group, logger):
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

    if len(group['expression']) % 2 == 0:
        logger.log("ERROR - postmigrate - lenght of group %s expression is even"
                   % group['path'], verbose=True)
        logger.log(entry, jsonData=True, verbose=True)
def processGroups(NSX, groupMaps, groups, logger, args):
    for gm in groupMaps['groups']:
        deleteGroups=[]
        logger.log("Checking group %s for temp groups" %gm['newUrl'], verbose=True)
        primaryGroup = NSX.list(api='/policy/api/v1'+gm['newUrl'], verbose=False)
        
        if 'new_internal_paths_to_delete' not in gm.keys():
            logger.log("Group %s does not have any temporary groups for clean up" % gm['newUrl'], False)
            addPostMigrateData(gm, primaryGroup, False)
            continue

        if len(gm['new_internal_paths_to_delete']) != len(gm['temp_apis']):
            logger.log("Group %s paths to delete doesn't equal # of temp apis" % gm['newUrl'], verbose=True)
        if not 'expression' in primaryGroup:
            logger.log("WARN - Group has %d temporary groups to clean up, but it doesn't have any membership expressions" %(gm['newUrl'], len(gm['new_internal_paths_to_delete'])))
            addPostMigrateData(gm, primaryGroup, False, gm['new_internal_paths_to_delete'])
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
            fixExpressions(primaryGroup, logger)
            if not found:
                logger.log("Group %s has temporary path %s that's not found in its expressions"
                           %(primaryGroup['path'], dg), verbose=True)

        logger.log("Updated group %s content: " %primaryGroup['path'], verbose=False)
        logger.log(primaryGroup, jsonData=True, jheader=True, verbose=False)
        addPostMigrateData( gm, primaryGroup, True)

    return groups

def submitGroups(NSX, data, logger, args):
    for gm in data['groups']:
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
            r = NSX.submitApi( api, g['body'], logger, args)
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

    '''
    slogger = Logger(file="postMigrateGroupResults.json", verbose=False)
    slogger.log(data, jsonData=True, jheader=False)
    slogger.close()
    '''
    
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

    logger.log("Retrieving group configs from %s" %args.migrationData, verbose=True)
    with open(args.migrationData, "r") as fp:
        groupMaps = json.load(fp)

    logger.log("Number of groups found in newGroups.json: %d"
               %len(groupMaps['groups']), verbose=True)
    migratedGroups = NSX.list(api='/policy/api/v1/infra/tags/effective-resources?scope=v_origin_site&tag=%s&filter_text=Group' % args.prefix, verbose=False)
    if migratedGroups['result_count'] == 0:
        logger.log("No groups found on NSX Manager %s that were migrated with prefix %s"
                   %(args.nsx, args.prefix), verbose=True)
    else:
        logger.log("Processing %d groups on NSX Manger %s that were migrated with prefix %s"
                   %(migratedGroups['result_count'], args.nsx, args.prefix), verbose=True)

    processGroups(NSX, groupMaps,
                  migratedGroups['results'],
                  logger, args)

    logger.log("Submitting changes to NSX: %s" %args.nsx, verbose=True)
    submitGroups(NSX, groupMaps, logger, args)
    slogger=Logger(file=args.postData, mode="w", verbose=False)
    slogger.log(groupMaps, jsonData=True, jheader=False, verbose=False)
    slogger.close()
    
    
if __name__=="__main__":
    main()
    
