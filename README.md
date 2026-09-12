# oMigrate

Python script to help with migrating pods & containers between servers.
Uses SSH for communication between source and destination server.

#### Functionality

- Communication via SSH.
- Image transfer between hosts, no need to redownload them.
- Volume Migration.
- Pod migration with all connected containers.
- Container migration.
- ENV file migration.
- Secrets migration (file based).
- Network aware migration (cannot create custom networks yet).

#### Installation

Download the latest version into a suitable folder on your system and then to get the script running you need to do some configuration in your system as well in the script.

##### System

The script needs a Python `venv` for best compatibility.

On Debian / Ubuntu the package needed is called `python3.xx-venv` and must be installed before continuing, for other systems adjust needed package and the commands below so that they work for you system.

Install package, replace `xx` with the version you want to install.

```bash
sudo apt install python3.xx-venv
```

##### Virtual Environment

The `venv` should always be created in the home folder of the user running the script.

When you are logged in to the user that should run the script change directory to the home folder.

```bash
cd ~/
```

Then run the following command, this will create a virtual environment just for this script.

```bash
python3 -m venv .venv/oMigrate
```
When the `venv` is created you need to install the `paramiko` Python package.

To install it do the following.

```bash
source .venv/oMigrate/bin/activate
pip3 install wheel
pip3 install paramiko
deactivate
```
Now the Python virtual environment is ready for use.

##### Script

The script needs som configuration so that it can do the work, each option to configure is explained within the script.

The top row in the script should point to your `venv` that you created before, for example if run as root it should look something like this.

```bash
#!/root/.venv/oMigrate/bin/python3
```

To run the script as an executable change the permission like this, make sure only the user running the script has permissions on it.

```bash
chmod 770 path/to/the/script/oMigrate.py
```

#### Usage

The script has a couple of input parameters that is required every time the script is run.

The following command line parameter takes either `pod` or `container` as value, this decides where to start the migration path going forward.

```bash
--type
```

The following command line parameter takes the name of the `pod` or `container` to migrate.

```bash
--name
```

The following command line parameter tells the script to what server to migrate the `pod` or `container` to.

```bash
--dst
```

The following command line parameter sets the port for SSH connection.

```bash
--port
```

The following command line parameter point out the name of the key file if `vSftpUseKeyFile` is set to `yes` and `vSftpKeyFilePath` is set, if using `username`/`password` this can be omitted.

```bash
--keyfile
```

#### Examples

When using the script for migration it is important that the path for `env` files and `secret` files is exactly the same on both servers or else it will not work.

Migrating a pod with SSH key:

```bash
./oMigrate --type "pod" --name "MyFantasticPod" --dst "newserver" --port "22" --keyfile "newserver.key"
```

Migrating a pod with username & password, will present an interactive prompt for SSH login:
```bash
./oMigrate --type "pod" --name "MyFantasticPod" --dst "newserver" --port "22"
```

Migrating a container with a SSH key:

```bash
./oMigrate --type "container" --name "MySingleContainer" --dst "newserver" --port "22" --keyfile "newserver.key"
```


Migrating a container with username & password, will present an interactive prompt for SSH login:
```bash
./oMigrate --type "container" --name "MySingleContainer" --dst "newserver" --port "22"
```

#### Security

The main security consideration is how the permissions is set on the script, always try to set as permissive as possible and use SSH keys if possible.

#### More

My homepage: [Link](https://www.osource.se)
