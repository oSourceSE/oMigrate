#!/usr/bin/python3

#################################################################
# Pod & Container migration script written in python.           #
# Home: https://www.osource.se/                                 #
# Author: Marcus Uddenhed                                       #
# Version: 1.3.1                                                #
# Date: 2024-04-08                                              #
# License: BSDL                                                 #
# Requirements: paramiko for SFTP                               #
# Command: pip3 install paramiko                                #
#################################################################

## Common parameters.

vMigrateDir: str = ""          # Where to put the files during migration for further processing, must be same path at receiving server.
vEnvDir: str = ""              # Where container env parameter files resides on both servers, must match on both sides and is not a temporary folder.
vSecDir: str = ""              # Secret directory where secret files reside during migration only, each file must match the secret name(s) used on the container.
vFilePrefix: str = "migrate"   # Prefix for backups during migration, do not add _ at the end, that is added later.
vSftpUseKeyFile: str = "No"    # Use a keyfile or username & password when connection to remote server.
vSftpKeyFilePath: str = ""     # Set to full path where your key files reside, only used if vSftpUseKeyFile is set to Yes.
vAcceptDisclaimer: str = "No"  # Set to Yes to not show the disclaimer, but please read it first.

#### Do not edit anything below this line ####

## Module Import
from datetime import datetime
import subprocess
import argparse
import paramiko
import getpass
import time
import sys
import re
import os

## Get required input parameters.
parser = argparse.ArgumentParser()
parser.add_argument('--type', required=True, dest='sType', type=str, help='Is it a container or a pod (values: pod/container).')
parser.add_argument('--name', required=True, dest='sName', type=str, help='Name of container or pod.')
parser.add_argument('--dst', required=True, dest='sDest', type=str, help='Destination server.')
parser.add_argument('--port', required=True, dest='sPort', type=str, help='Destination port.')
# Check what vSftpUseKeyFile is set to.
if vSftpUseKeyFile.lower() == "yes":
  parser.add_argument('--keyfile', required=True, dest='sKey', type=str, help='name of key file to use when connecting to remote server.')
elif vSftpUseKeyFile.lower() == "no":
  parser.add_argument('--keyfile', required=False, dest='sKey', type=str, help='name of key file to use when connecting to remote server.')
# Check argument length.
if len(sys.argv)==1:
  parser.print_help(sys.stderr)
  sys.exit(1)
args = parser.parse_args()
# Keep argument values for further processing.
vInputName: str = str(args.sName)
vInputType: str = str(args.sType)
vInputDest: str = str(args.sDest)
vInputPort: str = str(args.sPort)
vInputKey: str = str(args.sKey)

#### Global variables ####

## Define global variables and lists for later usage.

# Container create command.
vGlobContainerCreateCmd: str = None
# Pod create command.
vGlobPodCreateCmd: str = None
# Network name.
vGlobNetworkName: str = None
# Require list.
vGlobRequireList: list = []

#### General functions ####

## Function - Get current date.
def funcDateString() -> datetime:
  # Returns the today string year, month, day.
  return datetime.now().strftime("%Y%m%d")

# Function - Get current time.
def funcTimeString() -> datetime:
  # Returns the today string year, month, day.
  return datetime.now().strftime("%H:%M:%S")

# Function - General error message.
def funcErrorMsg(vType: str) -> None:
  print(
    "\n",
    "MIGRATION FAILED!!!",
    "If you are seeing this message it means that somewhere in the process the migration failed.\n",
    "The source " + vType + " still exits and can be used if needed so do not worry about that.\n",
    "\n",
    "Before trying to migrate again, you need to manually check what exists on the remote server \n",
    "and manually removing any files, settings specific to the failed migration.",
    "\n",
    "Remember to read the error message generated during the migration process, it can lead you to where things went wrong."
  )
  # Just return nothing, will output the word "None" if this do not exist.
  return ""

# Function - Yes/No
def funcYesNo(vQuestion: str) -> str:
  vReply: str = str(input(vQuestion+' (y/n): ')).lower().strip()
  if vReply[0] == 'y':
    return "1"
  if vReply[0] == 'n':
    return "0"
  else:
    return funcYesNo("Please enter only [y] or [n]...")

## Function - Disclaimer.
def funcDisclaimer() -> None:
  if vAcceptDisclaimer.lower() == "no":
    print(
      "Disclaimer!!!\n",
      "This script has been tested as much as possible, but there are no guarantees that it will work in every situation.\n",
      "The script uses built in podman commands to retrieve various information before proceeding.\n",
      "\n",
      "Beware that volumes that contain symlinks within the filesystem experience an issue with podman and can result in missing\n",
      "files on the destination server when a volume is restored.\n",
      "\n",
      "Path on local server and remote server must match 100% for the parameter vMigrateDir, this means that you need to\n",
      "have the same path on both servers.\n",
      "\n",
      "You need to run this script with the users running your containers both locally and for the remote SFTP session\n",
      "since this script tries to go the full line of migrating and starting the container at hand.\n",
      "\n",
      "To hide this disclaimer you can set the vAcceptDisclaimer parameter to Yes...\n",
      "\n",
      "Choose [y] to continue or choose [n] to exit.\n"
    )
    vGetOption: str = funcYesNo("Continue?")
    if vGetOption == "0":
      # Output exit message
      print("You choose to not continue with the migration.")
      exit(0)
    print("")
  else:
    print("Hide disclaimer is set to '" + vAcceptDisclaimer + "', skipping showing my nice disclaimer...")
  # Return nothing to remove it adding the word "None" to the output
  return ""

## Function - EndMessage
def funcEndMessage() -> None:
  # Build path return info.
  if len(vSecDir) != 0:
      vPath: str = vMigrateDir + ", " + vSecDir
  else:
    vPath: str = vMigrateDir
  # Determine if migration pod or single container.
  if vInputType.lower() == "container":
    print(
      "Migration Done!!!\n",
      "Please verify everything on the destination server.\n",
      "\n",
      "The container still exist on this server if migration failed on any step and can be restarted if needed.\n",
      "The local container needs to be manually removed when all test on migrated system is done and confirmed as working.\n",
      "\n",
      "The following folders needs to be cleaned out manually on both sides for now.\n",
      "Folder(s): " + vPath
    )
  elif vInputType.lower() == "pod":
    print(
      "Migration Done!!!\n",
      "Please verify everything on the destination server.\n",
      "\n",
      "The pod still exist on this server if migration failed on any step and can be restarted if needed.\n",
      "The local pod and attached containers needs to be manually removed when all test on migrated\n",
      "system is done and confirmed as working.\n",
      "\n",
      "The following folders needs to be cleaned out manually on both sides for now.\n",
      "Folder(s): " + vPath
    )
  # Return nothing to remove it adding the word "None" to the output
  return ""

## Function - Check migration folder.
def funcCheckMigrateFolder() -> None:
  print("Checking to see that migration folder is empty...")
  # Check status of folder.
  if os.listdir(vMigrateDir) == []:
    print("Folder is empty, continuing...")
  else:
    print("Folder is not empty, recommended not to continue without cleaning it first...")
    vGetOption: str = funcYesNo("Continue?")
    if vGetOption == "0":
      # Output message
      print("Halting migration...")
      exit(0)
    else:
      print("You chose to continue, errors generated from here on could be due to the migration folder not being empty...")
      time.sleep(5)
  # Just return nothing, will output the word "None" if this do not exist.
  return ""

#### SFTP Functions ####

## Function - Connect via SFTP.
def funcSftpConnect() -> None:
  try:
    global vScpClient
    vScpClient = paramiko.SSHClient()
    vScpClient.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    # Check if to ask for username & password or to use keyfile.
    if vSftpUseKeyFile.lower() == "no":
      print('Enter Username & Password for remote server...')
      vUser: str = input('Username: ')
      vPass: str = getpass.getpass('Password: ')
      vScpClient.connect(vInputDest, port=vInputPort, username=vUser, password=vPass)
    elif vSftpUseKeyFile.lower() == "yes":
      print('Using KeyFile to connect to remote server...')
      vKeyFile: str = paramiko.RSAKey.from_private_key_file(vSftpKeyFilePath + "/" + vInputKey)
      vScpClient.connect(vInputDest, port=vInputPort, pkey=vKeyFile, look_for_keys=False)
    # Open connection
    global vScpConn
    vScpConn = vScpClient.open_sftp()
    print('Connected to ' + vInputKey + '...')
  except:
    print('Cannot connect to remote server, exiting...')
    print(funcErrorMsg(vInputType.lower()))
    exit(1)

## Function - Send file via SFTP.
def funcSftpSend(vSftpFile: str, vShowMsg: str) -> None:
  try:
    print(vShowMsg)
    print('Sending file: ' + vSftpFile)
    vScpConn.put(vSftpFile, vSftpFile)
    print('Sent Ok...')
  except OSError as vErr:
    print('Could not send file...')
    print(vErr)

## Function - Run command via SFTP, return exit status and the message.
def funcSftpCmdRS(vSftpCmd: str, vShowMsg: str) -> list:
  try:
    print(vShowMsg)
    print("Command: " + vSftpCmd)
    stdin_, stdout_, stderr_ = vScpClient.exec_command(vSftpCmd)
    # Get exit status and return it.
    vStatus: str = stdout_.channel.recv_exit_status()
    vErrCode: int = stderr_.channel.recv_exit_status()
    if vErrCode != 0:
      vReturnMsg: str = "Error message:\n" + stderr_.read().decode("utf-8").strip()
      return vErrCode, vReturnMsg
    else:
      print("Done...")
      # To keep it consistent with 2 return statuses.
      vReturnMsg: str = "OK"
      return vStatus, vReturnMsg
  except OSError as vErr:
    print(vErr)

## Function - Run command via SFTP, return command status and response.
def funcSftpCmdRL(vSftpCmd: str, vShowMsg: str) -> list:
  try:
    print(vShowMsg)
    print("Command: " + vSftpCmd)
    stdin_, stdout_, stderr_ = vScpClient.exec_command(vSftpCmd)
    # Get returning lines.
    vLines: list = stdout_.readlines()
    # Get exit status.
    vStatus: int = stdout_.channel.recv_exit_status()
    vErrCode: int = stderr_.channel.recv_exit_status()
    if vErrCode != 0:
      vReturnMsg:str = "Error message:\n" + stderr_.read().decode("utf-8").strip()
      return vErrCode, vReturnMsg
    elif vErrCode == 0:
      if len(vLines) > 0:
        if vLines:
          for vLine in vLines:
            vClean01: str = re.sub("\\[\\'", '', vLine)
            vClean02: str = re.sub("\\'\\]\n", '', vClean01)
            vClean03:str  = re.sub("\n", '', vClean02)
            return vStatus, vClean03
      else:
        return vStatus, "None"
  except OSError as vErr:
    print(vErr)

## Function - Close SFTP connection.
def funcSftpClose() -> None:
  try:
    print("Closing remote session...")
    vScpConn.close()
    print("Remote session closed...")
  except OSError as vErr:
    print(vErr)

#### Container functions ####

## Function - Check if container exist locally, exit if not.
def funcContainerExistLocal() -> None:
  vCmdLine: str = "podman container inspect " + vInputName + " --format {{.Name}}"
  vRunCmd = subprocess.Popen(vCmdLine, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
  vCmdData: list = vRunCmd.stdout.readlines()
  if len(vCmdData) == 0:
    print("No matching container found, exiting...")
    print(funcErrorMsg("container"))
    exit(1)
  else:
    print("Local container exists, continuing...")

## Function - Check if container exist on remote server.
def funcContainerExistRemote(vName: str, vLoop: bool) -> int:
  vCmdLine: str = "podman container list --all --filter name=" + vName + " --format {{.Names}}"
  # Run the command and get status.
  vRemoteStatus: list = funcSftpCmdRL(vCmdLine, "Checking to see if container already exist on remote server...")
  if vRemoteStatus[1].strip() == vName:
    # If used in loop we shall not break script.
    if vLoop.lower() == "false":
      print("Container " + vRemoteStatus[1].strip() + " already exist on remote server, exiting...")
      print(funcErrorMsg("container"))
      exit(1)
    else:
        # Return status 1 for loop functions.
        return "1"
  else:
    print("Container do not seem to exist on remote server, continuing...")
    # Return status 0 for loop functions.
    return "0"

## Function - Get container create command.
def funcGetCntCreateCmd(vName: str) -> str:
  try:
    vCmdLine: str = "podman container inspect " + vName + " --format {{.Config.CreateCommand}}"
    vRunCmd = subprocess.Popen(vCmdLine, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    vCmdData: list = vRunCmd.stdout.readlines()
    for vCntCreate in vCmdData:
      vClean01: str = re.sub('\\[', '', vCntCreate.decode("utf-8").strip())
      vClean02: str = re.sub(']', '', vClean01)
      # Change "run" to "create" and remove "--detach"
      vClean03: str = vClean02.replace("run", "create")
      vClean04: str = vClean03.replace(" --detach", "")
      # Fix for custom sh start command with $ in them.
      vClean05: str = vClean04.replace('sh -c ', 'sh -c "')
      vClean06: str = vClean05.replace('$', '\$')
      # Add the final " at the end only if...
      if "sh -c" in vClean06:
        vClean07: str = vClean06 + '"'
        # Output.
        return vClean07
      else:
        # Output.
        return vClean06
  except:
    print("Cannot get create command, exiting...")
    print(funcErrorMsg("container"))
    exit(1)

## Function - Get volume names.
def funcGetCntVolName(vName: str) -> list:
  try:
    # Get create command.
    vGetCreateString: str = vGlobContainerCreateCmd
    # Return the volume if exist, else return None as value
    if '--volume' in str(vGetCreateString) or '-v' in str(vGetCreateString):
     # Volume Name List
      vNameList: list = []
      # CMD
      vCmdLine: str = "podman container inspect " + vName + " --format {{.Mounts}}"
      vRunCmd = subprocess.Popen(vCmdLine, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
      vCmdData: str = vRunCmd.stdout.readlines()
      vList: str = str(vCmdData[0])
      # Split the volume data.
      vSplit: list = vList.split('} {')
      # Loop through the data.
      for vRow in vSplit:
        # Clean the volume data.
        vCleanStart: str = re.sub('.*volume ', '', vRow)
        vCleanEnd: str = re.sub(' .*', '', vCleanStart)
        # Add to list.
        vNameList.append(vCleanEnd)
      # Return the finished list.
      return vNameList
    else:
      # If no volume exist return "None"
      return "None"
  except:
    # If we cannot get volume data at all exit.
    print("Error checking volume information, exiting...")
    print(funcErrorMsg("container"))
    exit(1)

## Function - Sync container between servers.
def funcSyncContainer(vName: str, vLoop: bool) -> list:
  try:
    print("Getting container '" + vName + "' create command...")
    vCreateCmd: str = vGlobContainerCreateCmd
    # Run the remote command and get result..
    vMessage: str = "Creating container '" + vName + "' on remote server..."
    vRemoteStatus: list = funcSftpCmdRS(vCreateCmd, vMessage)
    # Check return status.
    if vRemoteStatus[0] == 0:
      print("Container created on remote server...")
      return "0", "OK"
    else:
      if vLoop.lower() != "true":
        print("Cannot create container on remote server...")
        print(vRemoteStatus[1])
        print(funcErrorMsg("container"))
        exit(1)
      else:
        # Return that we could not create container.
        return "1", vRemoteStatus[1]
  except:
    print("Cannot migrate container, exiting...")
    print(funcErrorMsg("container"))
    exit(1)

## Function - Get container Pod membership.
def funcGetPodStatus() -> None:
  vCmdLine: str = "podman container inspect " + vInputName + " --format {{.Pod}}"
  vRunCmd = subprocess.Popen(vCmdLine, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
  vCmdData: str = vRunCmd.stdout.readlines()
  # Check length of returned data.
  vCmdDataExp: str = vCmdData[0].decode("utf-8").strip()
  if len(vCmdDataExp) > 1:
    # Get name from ID
    vCmdLine: str = "podman pod inspect " + vCmdDataExp + " --format {{.Name}}"
    vRunCmd: str = subprocess.Popen(vCmdLine, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    vCmdPod: str = vRunCmd.stdout.readlines()
    for vPodName in vCmdPod:
      # Output.
      print("This container is a member of the following pod: '" + vPodName.decode("utf-8").strip() + "', cannot migrate it as a single container, use Pod migration option instead, exiting...")
      print(funcErrorMsg("container"))
      exit(1)
  else:
    print("Not a member of a pod, continuing...")

## Function - Stop container.
def funcStopContainer() -> str:
  print("Stopping local container...")
  vCmdLine: str = "podman container stop " + vInputName
  vRunCmd = subprocess.Popen(vCmdLine, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
  vCmdOut: list = vRunCmd.stdout.readlines()
  vCmdErr: list = vRunCmd.stderr.readlines()
  if vCmdOut:
    for vData in vCmdOut:
      vName: str = vData.decode("utf-8").strip()
      if vName.lower() == vInputName.lower():
        return "Container stopped OK..."
      else:
        return vName
  if vCmdErr:
    for vError in vCmdErr:
      return vError.decode("utf-8").strip()

## Function - Start remote container.
def funcStartContainer(vName: str, vWait: int) -> None:
  # Run the command remote command.
  vCmdLine: str = "podman container start " + vName
  # Run command without asking for return status.
  vMessage: str = "Starting container '" + vName + "' on remote server..."
  funcSftpCmdRS(vCmdLine, vMessage)
  # Sleep on given time in seconds before checking status.
  print("Sleeping " + str(vWait) + " seconds before continuing...")
  time.sleep(vWait)
  # Check if container is running.
  vCmdCheckLine: str = "podman ps --filter name=" + vName + " --format {{.Status}}"
  # Run the command and get status.
  vRemoteStatus: list = funcSftpCmdRL(vCmdCheckLine, "Checking to see if the remote container is still running...")
  if vRemoteStatus[0] == 0:
    if "Up" in vRemoteStatus[1]:
      print("Container is running...")
    else:
      print("Could not get status of container, error message:\n", vRemoteStatus[1])

## Function - Volume Backup.
def funcVolumeBackup(vGetVolName: str) -> list:
  try:
    # Backup list.
    vFileList: list = []
    # Do the volume backups.
    for vName in vGetVolName:
      print("Backing up volume: ", vName)
      vCmdLine: str = "podman volume export --output"
      vSetTarFile=os.path.join(vMigrateDir, vFilePrefix + "_" + vName + "_" + funcDateString() + ".tar")
      # Execute export of volumes.
      vCmd: str = (vCmdLine + " " + vSetTarFile + " " + vName)
      subprocess.run(vCmd, shell=True, check=True)
      # Add to list.
      vFileList.append(vSetTarFile)
    # Return the list.
    return vFileList
  except:
    # Send info to console and exit.
    print("Could not export one or more volumes, exiting...")
    print(funcErrorMsg(vInputType.lower()))
    exit(1)

## Function - Transfer container image.
def funcImageSync(vName: str) -> None:
  try:
    ## Get container image
    print("Getting image from '" + vName + "' container...")
    vCmdLine: str = "podman container inspect " + vName + " --format {{.ImageName}}"
    vRunCmd = subprocess.Popen(vCmdLine, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    vCmdData: list = vRunCmd.stdout.readlines()
    for vImg in vCmdData:
      # Clean input.
      vImgSource: str =  vImg.decode("utf-8").strip()
    # CMD
    vCmdLine: str = "podman image inspect " + vImgSource + " --format {{.Id}}"
    # Get local image Id.
    vImgIdLocal = subprocess.run(vCmdLine, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    # Get remote image Id.
    vImgIdRemote: list = funcSftpCmdRL(vCmdLine, "Checking to see if image already exist on remote server...")
    # Check if images match.
    if vImgIdLocal.stdout.decode("utf-8").strip() == vImgIdRemote[1]:
      print("Image is already in sync, no need to transfer image...")
    else:
      ## Save image locally.
      print("Image is not synced...")
      print("Saving image '" + vImgSource + "' to file...")
      # Clean image name.
      vClean1: str = vImgSource.replace(".", "_")
      vClean2: str = vClean1.replace("/", "_")
      vName: str = vClean2.replace(":", "_")
      # CMD.
      vCmdLine: str = "podman image save --format docker-archive --quiet --output"
      # Build path & filename.
      vSetTarFile: str = os.path.join(vMigrateDir, vFilePrefix + "_img_" + vName + "_" + funcDateString() + ".tar")
      # Check if image already been saved, skip if yes.
      vFileExist: bool = os.path.isfile(vSetTarFile)
      if vFileExist != True:
        # Execute image save.
        vCmd: str = (vCmdLine + " " + vSetTarFile + " " + vImgSource)
        subprocess.run(vCmd, shell=True, check=True)
        # Send image to remote server.
        funcSftpSend(vSetTarFile, "Syncing image to remote server...")
        # Import image on remote server.
        vCmdImport: str = "podman image load --input " + vSetTarFile
        # Run the remote command and get result.
        vRemoteStatus: list = funcSftpCmdRS(vCmdImport, "Importing image on remote server...")
        if vRemoteStatus[0] != 0:
          print("Could not import image on remote server, error:\n", vRemoteStatus[1])
      else:
        print("Image export already exist in migration folder, assuming it has already been synced, skipping...")
  except:
    print("Could not sync container image, exiting...")
    print(funcErrorMsg("container"))
    exit(1)

## Function - Initialize containers.
def funcInitContainer(vName: str) -> None:
  try:
    vCmdInit: str = "podman init " + vName
    # Run the remote command and get result.
    vRemoteStatus: list = funcSftpCmdRS(vCmdInit, "Initializing container before restoring volumes to minimize issues with symlinks within volumes...")
    if vRemoteStatus[0] != 0:
      print("Could not Initialize the container on remote server, error:\n", vRemoteStatus[1])
  except OSError as vCmdErr:
    print("Cannot Initialize the following container: " + vName)
    print(vCmdErr)

## Function - Volume send and restore.
def funcVolSendRestore(vName: str, vType: str) -> None:
  try:
    # Determine if called for pod or container.
    if vType == "container":
      vWorkVolume = funcGetCntVolName(vName)
    elif vType == "pod":
      vWorkVolume = funcGetPodVolName(vName)
    # Check parameter status.
    if vWorkVolume != "None":
      # Backup returns the full filepath of every
      # volume backup taken for further processing.
      print("Checking '" + vName + "' for volumes...")
      vBackupVolFiles: list = funcVolumeBackup(vWorkVolume)
      # Send each backup.
      for vFile in vBackupVolFiles:
        funcSftpSend(vFile, "Sending volume backup...")
      # Restore volumes on remote machine.
      for vFile in vBackupVolFiles:
        vCleanStart: str = re.sub('.*\\/' + vFilePrefix + '\\_', '', vFile)
        vCleanEnd: str = re.sub('_' + '[0-9].*', '', vCleanStart)
        vCmd: str = "podman volume import " + vCleanEnd + ' ' + vFile
        # Run the remote command and get result.
        vRemoteStatus: list = funcSftpCmdRS(vCmd, "Importing volume on remote server...")
        if vRemoteStatus[0] != 0:
          print("Could not import volume on remote server, error:\n", vRemoteStatus[1])
    else:
      if vType == "container":
        print("Container '" + vName + "'has no volume(s) attached, continuing...")
      elif vType == "pod":
        print("Pod has no volume(s) attached, continuing...")
  except OSError as vCmdErr:
    print("Cannot restore the following volume: " + vCleanEnd)
    print(vCmdErr)

## Function - Check current env path against vEnvDir.
def funcGetContainerEnvFilePath() -> list:
  #vCntCreateString = funcGetCntCreateCmd(vName)
  vCntCreateString: str = vGlobContainerCreateCmd
  if "--env-file" in str(vCntCreateString):
    # Clean the env path.
    vClean01: str = re.sub('.*env\\-file ', '', vCntCreateString)
    vClean02: str = re.sub(' .*', '', vClean01)
    # Split and create a list
    vList: list = vClean02.split("/")
    # Remove first index in list.
    del vList[0]
    # Get length of list and subtract 1
    vLength: int = len(vList) - 1
    # Remove last index in list.
    del vList[vLength]
    # Merge list back to one string.
    vFinal: str = "/" + "/".join(vList)
    return vFinal

## Function - Check and sync env file if used.
def funcSyncContainerEnvFile() -> None:
  # Start with checking if vEnvDir is set.
  if len(vEnvDir) != 0:
    # Get global variable.
    vCreateString: str = vGlobContainerCreateCmd
    # Check if --env-file is used.
    if "--env-file" in str(vCreateString):
      print("Container '" + funcPodGetCntName() + "' has ENV file...")
      # Clean the env path.
      vClean01: str = re.sub('.*env\\-file ', '', vCreateString)
      vClean02: str = re.sub(' .*', '', vClean01)
      # Return current path.
      vFile: str = vClean02
      # Check if current path matches VEnvDir
      vContEnvFile: list = funcGetContainerEnvFilePath()
      if vContEnvFile == vEnvDir:
        # Check to see if a file with same name already exist on both sides.
        vCmdLine: str = "test -f " + vFile + " ; echo $?"
        # Run the command on local server and get status.
        vRunCmd = subprocess.Popen(vCmdLine, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        vCmdData: list = vRunCmd.stdout.readlines()
        if vCmdData[0].strip().decode("utf-8") == "1":
          print("No local ENV file found, exiting...")
          print(funcErrorMsg("container"))
          exit(1)
        else:
          print("Local ENV file exists, continuing...")
        # Run the command on remote server and get status.
        vRemoteStatus: list = funcSftpCmdRL(vCmdLine, "Checking to see if ENV file already exist on remote server...")
        vCleanRS: str = re.sub('\n', '', vRemoteStatus[1])
        if vCleanRS == "0":
          print("ENV file already exist on remote server, skipping sync...")
        elif vCleanRS == "1":
          print("ENV file do not exist on remote server...")
          # Sync env file to remote host.
          funcSftpSend(vFile, "Sending ENV file to remote server...")
      else:
        print("vEnvDir:", vEnvDir)
        print("Container:", vContEnvFile)
        print("Different sources for ENV file, container not matching vEnvDir variable, exiting...")
        print(funcErrorMsg("container"))
        exit(1)
    else:
      print("Container '" + funcPodGetCntName() + "' has no ENV file, continuing...")
  else:
    print("Not using vEnvDir parameter, will not check for ENV file on containers...")

## Function - Check and sync container secrets.
def funcSyncContainerSecret(vName: str) -> None:
  # Get global parameter
  vCreateString: str = vGlobContainerCreateCmd
  print("Checking '" + vName + "' for secret(s)...")
  # Check to see if secret is used.
  if "--secret" in str(vCreateString):
    # check if vSecDir is set.
    if len(vSecDir) != 0:
      # List for secrets
      vAllSecrets: list = []
      # Get every secret name from container
      vSplit: list = vCreateString.split(" --")
      for vSecret in vSplit:
        if "secret " in vSecret:
          vClean01: str = re.sub('secret ', '', vSecret)
          vClean02: str = re.sub('\\,.*', '', vClean01)
          vAllSecrets.append(vClean02)
      # Remove brackets from list for presentation.
      vSecList: list = str(vAllSecrets)[1:-1]
      # List for return statuses
      vSecRStatus: list = []
      # Check to see if there are a secret file(s) for the container under vSecDir.
      for vSec in vAllSecrets:
        vCmdLine: str = "test -f " + vSecDir + "/" + vSec + " ; echo $?"
        vRunCmd = subprocess.run(vCmdLine, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        # Get return status.
        vSecRStatus.append(int(vRunCmd.stdout.decode("utf-8").strip()))
      # Check return status
      if 1 in vSecRStatus:
        # When secret file do not exist.
        print("Missing secret file and container is using secret parameter(s).")
        print("You can choose to continue, ignoring secret sync, this is ok only IF you already")
        print("have created the secret(s) on the destination server, otherwise the container will fail to start.")
        if len(vSecRStatus) > 1:
          print("Make sure they are named correctly, same as when the container was created.")
          print("This is what we found:", vSecList)
        else:
          print("Make sure you named it correct, this is what we found:", vSecList)
        input("To continue without secret file choose [y] or choose [n] to halt migration.")
        vGetOption: str = funcYesNo("Continue?")
        if vGetOption == "0":
          # Output error message
          print(funcErrorMsg("container"))
          exit(1)
      elif 0 in vSecRStatus:
        # Iterate through all of the secrets, send and import them one by one.
        for vSec in vAllSecrets:
          # Check path on remote server.
          vCmdLine: str = "test -d " + vSecDir + " ; echo $?"
          vRemoteStatus: list = funcSftpCmdRL(vCmdLine, "Checking that remote path exist and matches vSecDir parameter...")
          vCleanRS: str = re.sub('\n', '', vRemoteStatus[1])
          if vCleanRS == "0":
            # Send Secret file over to remote server.
            vFilePath: str = vSecDir + "/" + vSec
            funcSftpSend(vFilePath,"Sending secret..")
            # Import secret on remote server.
            vCmdLine: str = "podman secret create " + vSec + " " + vSecDir + "/" + vSec
            # import secret into secret store.
            vRemSecStatus: list = funcSftpCmdRL(vCmdLine,"Creating secret on remote server...")
            # Checking return status.
            if vRemSecStatus[0] != 0:
              print("Could not create the following secret:", vSec)
              print("Error from remote command:\n")
              print(vRemSecStatus[1].strip() + "\n")
              if "secret name in use" in vRemSecStatus[1]:
                print("If the secret on the remote server is for this container you can choose to continue.")
                input("To continue using the existing secret choose [y] or choose [n] to halt migration.")
                vGetOption: str = funcYesNo("Continue?")
                if vGetOption == "0":
                  # Output error message
                  print(funcErrorMsg("container"))
                  exit(1)
              elif "no such file or directory" in vRemSecStatus[1]:
                print("Did we send the files properly?, check status further up...")
                print("Cannot continue, exiting...")
                print(funcErrorMsg("container"))
                exit(1)
              else:
                print("Unknown error, cannot continue, exiting...")
                print(funcErrorMsg("container"))
                exit(1)
            else:
              print("Secret imported on remote server...")
          elif vCleanRS == "1":
            print("Remote directory do not exist, please validate, exiting...")
            print(funcErrorMsg("container"))
            exit(1)
    else:
      # When vSecDir is not set.
      print("Container is using --secret parameter(s) but vSecDir is not set.")
      print("You can choose to continue, ignoring secret sync, this is ok only IF you already")
      print("have created the secret on the destination server, otherwise the container will fail to start.")
      input("To continue without syncing secret choose [y] or choose [n] to halt migration.\n")
      vGetOption: str = funcYesNo("Continue?")
      if vGetOption == "0":
        # Output error message
        print(funcErrorMsg("container"))
        exit(1)
  else:
    print("Container '" + funcPodGetCntName() + "' is not using secrets, continuing...")

## Function - Check and sync network.
def funcSyncNetwork(vName: str) -> str:
  # Get global variable.
  vCreateString: str = vGlobContainerCreateCmd
  # Check to see if the network option is used.
  if '--network ' in vGlobContainerCreateCmd:
    print("The container '" + vName + "' uses the --network option...")
    # Get network name.
    vClean01: str = re.sub('.*network ', '', vCreateString)
    vClean02: str = re.sub(' .*', '', vClean01)
    # Return network name.
    vNetName: str = vClean02
    # Check to see if we already created the network as per pod migration.
    global vGlobNetworkName
    if vGlobNetworkName != vNetName:
      # Check to see if it exist on remote server.
      vCmdLine: str = "podman network inspect " + vNetName + " --format {{.Name}}"
      vRemoteStatus: list = funcSftpCmdRL(vCmdLine, "Checking to see if network already exist on remote server...")
      if vRemoteStatus[1] == vNetName:
        # Give some options
        print(
          "\n"
          "Network already exists on remote server...\n"
          "Is the network configured on the remote server for this container?\n"
          "If the network is for this container you can choose [y] to continue,\n"
          "and to use existing network, else choose [n] to halt the migration process.\n"
        )
        vGetOption: str = funcYesNo("Continue?")
        if vGetOption == "0":
          # Output error message
          print(funcErrorMsg("container"))
          exit(1)
        else:
          # Add network name to global.
          vGlobNetworkName = vNetName
      else:
        # Give some options.
        print(
          "The network do not exist on the remote server...\n"
          "\n"
          "Either we can create it for you giving it default settings, OR\n"
          "if you created it with custom, ip-range, subnet mask and so on you need to\n"
          "manually create the network on the remote server before continuing.\n"
          "\n"
          "Choose [y] to let us create the network or choose [n] when you have\n"
          "manually created the network on the remote server to continue."
        )
        vGetOption: str = funcYesNo("Let us create the network?")
        if vGetOption == "1":
          # Add network name to global.
          vGlobNetworkName = vNetName
          # Create network
          vPrint: str = "\nCreating '" + vNetName + "' network on remote server..."
          vCmdLine: str = "podman network create " + vNetName
          vRemoteStatus: list = funcSftpCmdRL(vCmdLine, vPrint)
          if vRemoteStatus[1] == vNetName:
            print("Network created, continuing...")
          else:
            print("Cold not create network...")
            print("Error from command:\n", vRemoteStatus)
            print("Halting further migrations steps, exiting...")
            exit(1)
        else:
          print("Continuing without creating the network on the remote server...")
          # Add network name to global.
          vGlobNetworkName = vNetName
    else:
      print("Network '" + vNetName + "' already created or skipped in this migration. continuing...")
  else:
    print("Container '" + vName + "' Not using network, continuing...")

#### Pod functions ####

## Function - Check if pod exist.
def funcPodExistLocal(vName: str) -> None:
  vCmdLine: str = "podman pod inspect " + vName + " --format {{.Name}}"
  vRunCmd = subprocess.Popen(vCmdLine, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
  vCmdData: list = vRunCmd.stdout.readlines()
  if len(vCmdData) == 0:
    print("No matching pod found, cannot continue, exiting...")
    print(funcErrorMsg("pod"))
    exit(1)
  else:
    print("Pod exists on local server, continuing...")

## Function - Pod exist on remote server.
def funcPodExistRemote(vName: str) -> None:
  vCmdLine: str = "podman pod inspect " + vName + " --format {{.Name}}"
  vRemoteStatus: list = funcSftpCmdRL(vCmdLine, "Checking to see if container already exist on remote server...")
  if vRemoteStatus[0] != "0":
    if vRemoteStatus[1].strip() == vName:
      print("Pod already exist on remote server, exiting...")
      print(funcErrorMsg("pod"))
      exit(1)
    else:
      print("Container do not seem to exist on remote server, continuing...")

## Function - Get pod create command.
def funcGetPodCreateCmd(vName: str) -> str:
  try:
    vCmdLine: str = "podman pod inspect " + vName + " --format {{.CreateCommand}}"
    vRunCmd = subprocess.Popen(vCmdLine, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    vCmdData: list = vRunCmd.stdout.readlines()
    for vPodCreate in vCmdData:
      vCleanStart: str = re.sub('\\[', '', vPodCreate.decode("utf-8").strip())
      vCleanEnd: str = re.sub(']', '', vCleanStart)
      # Output.
      return vCleanEnd
  except:
    print("Cannot get create command, exiting...")
    print(funcErrorMsg("pod"))
    exit(1)

## Function - Get pod containers.
def funcGetPodContainers(vName: str) -> list:
  try:
    # Name list
    vNameList: list = []
    # CMD
    vCmdLine: str = "podman pod inspect " + vName + " --format {{.Containers}}"
    vRunCmd = subprocess.Popen(vCmdLine, text=True, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    vCmdList: list = vRunCmd.stdout.readlines()
    vData = str(vCmdList[0])
    # Format data
    vSplit: list = vData.split('} {')
    for vRow in vSplit:
      vClean1: str = re.sub('^\S+ ', '', vRow)
      vClean2: str = re.sub(' .*', '', vClean1)
      vClean3: str = re.sub('\n', '', vClean2)
      # Add to list.
      if "infra" not in vClean3:
        vNameList.append(vClean3)
    # Output.
    return vNameList
  except:
    print("Cannot get pod containers, exiting...")
    print(funcErrorMsg("pod"))
    exit(1)

## Function - Sync every container image on pod.
def funcSyncPodImages(vName: str) -> None:
  # Get containers.
  vListContainers: list = funcGetPodContainers(vName)
  # Do for every container
  for vList in vListContainers:
    funcImageSync(vList)

## Function - Sync pod between servers.
def funcSyncPod() -> None:
  try:
    print("Getting pod create command...")
    vCreateCmd: str = vGlobPodCreateCmd
    # Run the remote command and get result.
    vRemoteStatus: list = funcSftpCmdRS(vCreateCmd, "Creating pod on remote server...")
    if vRemoteStatus[0] != 0:
      print("Could not create pod, command, error:\n", vRemoteStatus[1])
      print(funcErrorMsg("pod"))
      exit(1)
  except:
    print("Cannot sync pod, exiting...")
    print(funcErrorMsg("pod"))
    exit(1)

## Function - Get pod volume names.
def funcGetPodVolName(vName: str) -> list:
  try:
    # Get create command.
    #vGetCreateString = funcGetCntCreateCmd(vName)
    vGetCreateString: str = vGlobPodCreateCmd
    # Return the volume if exist, else return None as value
    if '--volume' in str(vGetCreateString) or '-v' in str(vGetCreateString):
     # Volume Name list
      vNameList: list = []
      # CMD
      vCmdLine: str = "podman pod inspect " + vName + " --format {{.Mounts}}"
      vRunCmd = subprocess.Popen(vCmdLine, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
      vCmdData: str = vRunCmd.stdout.readlines()
      vList: str = str(vCmdData[0])
      # Split the volume data.
      vSplit: list = vList.split('} {')
      # Loop through the data.
      for vRow in vSplit:
        # Clean the volume data.
        vCleanStart: str = re.sub('.*volume ', '', vRow)
        vCleanEnd: str = re.sub(' .*', '', vCleanStart)
        # Add to list.
        vNameList.append(vCleanEnd)
      # Return the finished list.
      return vNameList
    else:
      # If no volume exist return "None"
      return "None"
  except:
    # If we cannot get volume data at all exit.
    print("Error checking volume information, exiting...")
    print(funcErrorMsg("pod"))
    exit(1)

## Function - Create containers on remote server.
def funcSyncPodContainers() -> None:
  # Set to global.
  global vGlobContainerCreateCmd
  # Loop until vGlobRequireList is empty.
  while len(vGlobRequireList) != 0:
    # Do for every container.
    for vCntList in vGlobRequireList:
      # Split the data.
      vDep: list = re.split(":", vCntList)
      # Assign each index to a variable
      vDepP1: str = vDep[0]
      vDepP2: str = vDep[1]
      vDepP3: str = vDep[2]
      vDepP4: str = vDep[3]
      # Check if it has dependencies to other containers
      if vDepP2 == "1" and len(vGlobRequireList) != 1:
        print("Container '" + vDepP1 + "' has dependencies...")
        # Create list with required containers.
        vReqList: list = re.split(",", vDepP4)
        # Iterate through requirements list.
        for vList in vReqList:
          # State what container we are working on.
          print("Starting migration for '" + vList + "' container...")
          # Check if dependencies are met
          vRemoteStatus: int = funcContainerExistRemote(vList,"true")
          if vRemoteStatus[0] == "1":
            print("Container '" + vList +  "' already exist on remote server, setting as migrated..")
            # Remove from list when classified as migrated.
            if vList in vGlobRequireList:
              vGlobRequireList.remove(vList)
          else:
            # Try to migrate
            print("Migrating '" + vList + "' to remote server...")
            # Manipulate global variable for each container.
            vGlobContainerCreateCmd = funcGetCntCreateCmd(vList)
            # Sync container.
            vGetStatus: list = funcSyncContainer(vList,"true")
            # Check return status, if it complains about missing requirements,
            if "cannot be used as a dependency" in vGetStatus[1]:
              # What to do when requirement is not meet.
              print("Requirements not satisfied for '" + vList + "', will continue and come back to this one again...")
            elif "OK" in vGetStatus[1]:
              # What to do when requirement is meet...
              # Initialize container.
              funcInitContainer(vList)
              # Migrate volumes...
              funcVolSendRestore(vList,"container")
              # Start container...
              funcStartContainer(vList,10)
              # Remove from list when classified as migrated.
              vReqList.remove(vList)
              # Remove from global list.
              vMigSearch: str = list(filter(lambda x: x.startswith(vList), vGlobRequireList))
              vMSClean01: str = re.sub("\\[\\'","",str(vMigSearch))
              vMSClean02: str = re.sub("\\'\\]","",vMSClean01)
              vGlobRequireList.remove(vMSClean02)
              print("Container '" + vList + "' migrated...")
              print("-")
            else:
              print("Unknown error, cannot continue, exiting...")
              print(vGetStatus[1])
              print(funcErrorMsg("pod"))
              exit(1)
      else:
        # State what container we are working on.
        print("Starting migration for '" + vDepP1 + "' container...")
        # Here we migrate the container when it has no dependencies.
        print("No dependencies lingering for '" + vDepP1 + "', migrating container...")
        # Manipulate global variable for each container.
        vGlobContainerCreateCmd = funcGetCntCreateCmd(vDepP1)
        # Sync container.
        vGetStatus: list = funcSyncContainer(vDepP1,"true")
        # Initialize container.
        funcInitContainer(vDepP1)
        # Migrate volumes...
        funcVolSendRestore(vDepP1,"container")
        # Start container...
        funcStartContainer(vDepP1,10)
        # Remove from global list.
        vGlobRequireList.remove(vCntList)
        # Final message.
        print("Container '" + vDepP1 + "' migrated...")
        print("-")

## Function - Check and sync env file if used.
def funcSyncPodEnvFiles() -> None:
  # Get containers.
  vListContainers: list = funcGetPodContainers(vInputName)
  # Do for every container
  for vList in vListContainers:
    # Manipulate global variable for each container.
    global vGlobContainerCreateCmd
    vGlobContainerCreateCmd = funcGetCntCreateCmd(vList)
    # Sync env file.
    funcSyncContainerEnvFile()

## Function - Sync and import secret file if used.
def funcSyncPodSecFiles(vName: str) -> None:
  # Get containers.
  vListContainers: list = funcGetPodContainers(vName)
  # Do for every container
  for vList in vListContainers:
    # Manipulate global variable for each container.
    global vGlobContainerCreateCmd
    vGlobContainerCreateCmd = funcGetCntCreateCmd(vList)
    # Sync env file.
    funcSyncContainerSecret(vList)

## Function - Start remote pod.
def funcStartPod(vName: str, vWait: int) -> None:
  vCmdLine: str = "podman pod start " + vName
  # Run the remote command and get result.
  vMessage: str = "Trying to start '" + vName + "' on remote server if not already started..."
  vRemoteStatus: list = funcSftpCmdRS(vCmdLine, vMessage)
  if vRemoteStatus[0] != 0:
      print("Could not start pod, error:\n", vRemoteStatus[1])
  # Sleep on given time in seconds before checking status.
  print("Sleeping " + str(vWait) + " seconds before continuing...")
  time.sleep(vWait)
  # Check if container is running.
  vCmdCheckLine: str = "podman pod ps --filter name=" + vName + " --format {{.Status}}"
  vRemoteStatus: list = funcSftpCmdRL(vCmdCheckLine, "Checking to see if the pod is still running...")
  if "Running" in vRemoteStatus[1]:
    print("Container seems to be running...")
  elif "Degraded" in vRemoteStatus[1]:
    print("Please check status on remote server, current status:", vRemoteStatus)
  elif "Exited" in vRemoteStatus[1]:
    print("Please check status on remote server, current status:", vRemoteStatus)

## Function - Stop pod.
def funcStopPod() -> str:
  print("Stopping local pod...")
  vCmdLine: str = "podman pod stop " + vInputName
  vRunCmd = subprocess.Popen(vCmdLine, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
  vCmdOut: list = vRunCmd.stdout.readlines()
  vCmdErr: list = vRunCmd.stderr.readlines()
  if vCmdOut:
    for vData in vCmdOut:
      vName: str = vData.decode("utf-8").strip()
      if vName.lower() == vInputName.lower():
        return "Pod stopped OK..."
      else:
        return vName
  if vCmdErr:
    for vError in vCmdErr:
      return vError.decode("utf-8").strip()

## Function - Get container name.
def funcPodGetCntName() -> str:
  # Get create command from global.
  vGetCmd: str = vGlobContainerCreateCmd
  # Clean string.
  vClean01: str = re.sub('.*\\--name ', '', vGetCmd)
  vClean02: str = re.sub(' .*', '', vClean01)
  return vClean02

## Function - Sync each container network.
def funcPodSyncNetwork(vName: str) -> None:
  # Get containers.
  vListContainers: list = funcGetPodContainers(vName)
  # Do for every container
  for vList in vListContainers:
    # Manipulate global variable for each container.
    global vGlobContainerCreateCmd
    vGlobContainerCreateCmd = funcGetCntCreateCmd(vList)
    # Sync networks.
    funcSyncNetwork(vList)

## Function - Require list.
def funcPodCntRequire(vName: str) -> None:
  # Get containers.
  vListContainers = funcGetPodContainers(vName)
  # Do for every container
  for vList in vListContainers:
    # Check if they have the --require option.
    vCreate = funcGetCntCreateCmd(vList)
    if "--requires " in vCreate:
      # Clean the data.
      vCleanStart = re.sub('.*requires ', '', vCreate)
      vCleanEnd = re.sub(' .*', '', vCleanStart)
      # Add to list (Format: Name:Require:Migrated:Containers)
      vListElement = vList + ":1:0:" + vCleanEnd
      vGlobRequireList.append(vListElement)
    else:
      # Add to list (Format: Name:Require:Migrated:Containers)
      vListElement = vList + ":0:0:None"
      vGlobRequireList.append(vListElement)

#### Main functions to bind all things together ####

## Function - Container Job.
def funcContainerJob() -> None:
  ## PreFlight Steps.
  # Step 1 - Show disclaimer if vAcceptDisclaimer is set to no.
  print("-- Step 1: TimeStamp:", funcTimeString())
  funcDisclaimer()
  # Step 2 - Check migration folder.
  print("\n-- Step 2: TimeStamp:", funcTimeString())
  funcCheckMigrateFolder()
  # Step 3 - Check if local Container exist, exit if not.
  print("\n-- Step 3: TimeStamp:", funcTimeString())
  funcContainerExistLocal()
  # Step 4 - See if the local container is a member of a pod, exit if it is.
  print("\n-- Step 4: TimeStamp:", funcTimeString())
  funcGetPodStatus()
  # Step 5 - Fill globals with value.
  print("\n-- Step 5: TimeStamp:", funcTimeString())
  print("Assigning global parameters...")
  global vGlobContainerCreateCmd
  vGlobContainerCreateCmd = funcGetCntCreateCmd(vInputName)

  ## Time to work
  # Step 6 - Connect to remote server.
  print("\n-- Step 6: TimeStamp:", funcTimeString())
  funcSftpConnect()
  # Step 7 - Check if container exist on remote server.
  print("\n-- Step 7: TimeStamp:", funcTimeString())
  funcContainerExistRemote(vInputName,"false")
  # Step 8 - Check if network is used.
  print("\n-- Step 8: TimeStamp:", funcTimeString())
  funcSyncNetwork(vInputName)
  # Step 9 - Sync env file to remote server.
  print("\n-- Step 9: TimeStamp:", funcTimeString())
  funcSyncContainerEnvFile()
  # Step 10 - Sync local container image to remote server.
  print("\n-- Step 10: TimeStamp:", funcTimeString())
  funcImageSync(vInputName)
  # Step 11 - Transfer secrets to remote server.
  print("\n-- Step 11: TimeStamp:", funcTimeString())
  funcSyncContainerSecret(vInputName)
  # Step 12 - Create container on remote server.
  print("\n-- Step 12: TimeStamp:", funcTimeString())
  funcSyncContainer(vInputName,"false")
  # Step 13 - Initialize container.
  print("\n-- Step 13: TimeStamp:", funcTimeString())
  funcInitContainer(vInputName)
  # Step 14 - Stop local container.
  print("\n-- Step 14: TimeStamp:", funcTimeString())
  funcStopContainer()
  # Step 15 - Backup volumes if there are any & send to remote server.
  print("\n-- Step 15: TimeStamp:", funcTimeString())
  funcVolSendRestore(vInputName,"container")
  # Step 16 - Start container on remote server.
  print("\n-- Step 16: TimeStamp:", funcTimeString())
  funcStartContainer(vInputName,10)
  # Step 17 - End SFTP connection.
  print("\n-- Step 17: TimeStamp:", funcTimeString())
  funcSftpClose()
  # Step 18 - Finally done.
  print("\n-- Step 18: TimeStamp:", funcTimeString())
  funcEndMessage()

## Function - Pod Job.
def funcPodJob() -> None:
  ## PreFlight Steps
  # Step 1 - Show disclaimer if vAcceptDisclaimer is set to no.
  print("-- Step 1: TimeStamp:", funcTimeString())
  funcDisclaimer()
  # Step 2 - Check migration folder.
  print("\n-- Step 2: TimeStamp:", funcTimeString())
  funcCheckMigrateFolder()
  # Step 3 - Check if Pod exist, will exit if not.
  print("\n-- Step 3: TimeStamp:", funcTimeString())
  funcPodExistLocal(vInputName)
  # Step 4 - Fill globals with value.
  print("\n-- Step 4: TimeStamp:", funcTimeString())
  print("Assigning global parameters...")
  global vGlobPodCreateCmd
  vGlobPodCreateCmd = funcGetPodCreateCmd(vInputName)
  funcPodCntRequire(vInputName)

  ## Time to work
  # Step 5 - Connect to remote server.
  print("\n-- Step 5: TimeStamp:", funcTimeString())
  funcSftpConnect()
  # Step 6 - Check if pod exist on remote server.
  print("\n-- Step 6: TimeStamp:", funcTimeString())
  funcPodExistRemote(vInputName)
  # Step 7 - Check if pod exist on remote server.
  print("\n-- Step 7: TimeStamp:", funcTimeString())
  funcPodSyncNetwork(vInputName)
  # Step 8 - Sync Container images for pod containers.
  print("\n-- Step 8: TimeStamp:", funcTimeString())
  funcSyncPodImages(vInputName)
  # Step 9 - Create pod on remote server.
  print("\n-- Step 9: TimeStamp:", funcTimeString())
  funcSyncPod()
  # Step 10 - Sync env files to remote server.
  print("\n-- Step 10: TimeStamp:", funcTimeString())
  funcSyncPodEnvFiles()
  # Step 11 - Transfer secrets to remote server.
  print("\n-- Step 11: TimeStamp:", funcTimeString())
  funcSyncPodSecFiles(vInputName)
  # Step 12 - Stop pod.
  print("\n-- Step 12: TimeStamp:", funcTimeString())
  funcStopPod()
  # Step 13 - Backup and sync pod volume(s)
  print("\n-- Step 13: TimeStamp:", funcTimeString())
  funcVolSendRestore(vInputName,"pod")
  # Step 14 - Create containers on remote server.
  print("\n-- Step 14: TimeStamp:", funcTimeString())
  funcSyncPodContainers()
  # Step 15 - Start remote pod.
  print("\n-- Step 15: TimeStamp:", funcTimeString())
  funcStartPod(vInputName, 20)
  # Step 16 - End SFTP connection.
  print("\n-- Step 16 TimeStamp:", funcTimeString())
  funcSftpClose()
  # Step 17 - Finally done.
  print("\n-- Step 17: TimeStamp:", funcTimeString())
  funcEndMessage()

### Function - Main
def funcMain() -> None:
  #### vInputType = Container ####
  if vInputType.lower() == "container":
    funcContainerJob()
  #### vInputType = Pod ####
  if vInputType.lower() == "pod":
    funcPodJob()

## Execute funcMain to Run the whole shebang....
if __name__ == '__main__':
    funcMain()
