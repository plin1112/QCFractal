import atexit
import shutil
import subprocess
import tempfile
import time
from typing import Any, Dict, List, Union, Optional

import psycopg2

from .config import FractalConfig
from .util import find_port, is_port_open


class PostgresHarness:
    def __init__(self, config: Union[Dict[str, Any], FractalConfig], quiet: bool = True, logger: 'print' = print):
        """A flexible connection to a PostgreSQL server

        Parameters
        ----------
        config : Union[Dict[str, Any], FractalConfig]
            The configuration options
        quiet : bool, optional
            If True, does not log any operations
        logger : print, optional
            The logger to show the operations to.
        """
        if isinstance(config, dict):
            config = FractalConfig(**config)
        self.config = config
        self.quiet = quiet
        self.logger = logger
        self._checked = False

    def _run(self, commands):
        proc = subprocess.run(commands, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout = proc.stdout.decode()
        if not self.quiet:
            self.logger(stdout)

        ret = {"retcode": proc.returncode, "stdout": stdout, "stderr": proc.stderr.decode()}

        return ret

    def _check_psql(self) -> None:
        """
        Checks to see if the proper PostgreSQL commands are present. Raises a ValueError if they are not found.
        """

        if self.config.database.host != "localhost":
            raise ValueError(f"Cannot modify PostgreSQL as configuration points to non-localhost: {self.config.host}")

        if self._checked:
            return

        msg = """
Could not find 'pg_ctl' in the current path. Please install PostgreSQL with 'conda install postgresql'.

Alternatively, you can install a system PostgreSQL manually, please see the following link: https://www.postgresql.org/download/
"""

        if shutil.which("pg_ctl") is None:
            raise ValueError(msg)
        else:
            self._checked = True

    def database_uri(self) -> str:
        """Provides the full PostgreSQL URI string.

        Returns
        -------
        str
            The database URI
        """
        return self.config.database_uri(safe=False, database="")

    def connect(self, database: Optional[str] = None) -> 'Connection':
        """Builds a psycopg2 connection object.

        Parameters
        ----------
        database : Optional[str], optional
            The database to connect to, otherwise defaults to None

        Returns
        -------
        Connection
            A live Connection object.
        """
        if database is None:
            database = "postgres"
        return psycopg2.connect(
            database=database,
            # user=self.config.database.username,
            host=self.config.database.host,
            port=self.config.database.port)

    def is_alive(self, database: Optional[str] = None) -> bool:
        """Checks if the postgres is alive, and optionally if the database is present.

        Parameters
        ----------
        database : Optional[str], optional
            The datbase to connect to

        Returns
        -------
        bool
            If True, the postgres database is alive.
        """
        try:
            self.connect(database=database)
            return True
        except psycopg2._psycopg.OperationalError:
            return False

    def command(self, cmd: str) -> Any:
        """Runs psql commands and returns their output while connected to the correct postgres instance.

        Parameters
        ----------
        cmd : str
            A psql command string.
            Description

        """
        self._check_psql()

        if not self.quiet:
            self.logger(f"pqsl command: {cmd}")
        psql_cmd = [shutil.which("psql"), "-p", str(self.config.database.port), "-c"]
        return self._run(psql_cmd + [cmd])

    def pg_ctl(self, cmds: List[str]) -> Any:
        """Runs pg_ctl commands and returns their output while connected to the correct postgres instance.

        Parameters
        ----------
        cmds : List[str]
            A list of PostgreSQL pg_ctl commands to run.
        """
        self._check_psql()

        if not self.quiet:
            self.logger(f"pg_ctl command: {cmds}")
        psql_cmd = [shutil.which("pg_ctl"), "-D", str(self.config.database_path)]
        return self._run(psql_cmd + cmds)

    def create_database(self, database_name: str) -> bool:
        """Creates a new database for the current postgres instance. If the database is existing, no
        changes to the database are made.

        Parameters
        ----------
        database_name : str
            The name of the database to create.

        Returns
        -------
        bool
            If the operation was successful or not.
        """
        conn = self.connect()
        conn.autocommit = True

        cursor = conn.cursor()
        cursor.execute(f"SELECT 1 FROM pg_catalog.pg_database WHERE datname = '{database_name}'")
        exists = cursor.fetchone()

        if not exists:
            cursor.execute(f"CREATE DATABASE {database_name}")

        return self.is_alive(database=database_name)

    def start(self) -> Any:
        """
        Starts a PostgreSQL server based off the current configuration parameters. The server must be initialized
        and the configured port open.
        """

        self._check_psql()

        # Startup the server
        if not self.quiet:
            self.logger("Starting the database:")

        if is_port_open(self.config.database.host, self.config.database.port):
            if not self.quiet:
                self.logger("Service currently running the configured port, current_status:\n")
            status = self.pg_ctl(["status"])

            # If status is ok, exit is 0
            if status["retcode"] != 0:
                raise ValueError(
                    f"A process is already running on 'port:{self.config.database.port}` that is not associated with the PostgreSQL instance at `location:{self.config.database.directory}.`"
                    "\nThis often happens when two PostgreSQL databases are attempted to run on the same port."
                    "\nEither shut down the other PostgreSQL database or change the `qcfractal-server init --db-port`."
                    "\nStopping."
                )

            if not self.is_alive():
                raise ValueError(f"PostgreSQL is running, but cannot connect to the default port.")

            if not self.quiet:
                self.logger("Found running PostgreSQL instance with correct configuration.")

        else:
            start_status = self.pg_ctl([
                "-l", str(self.config.database_path / self.config.database.logfile),
                "start"]) # yapf: disable

            if not (("server started" in start_status["stdout"]) or ("server starting" in start_status["stdout"])):
                raise ValueError(f"Could not start the PostgreSQL server. Error below:\n\n{start_status['stderr']}")

            # Check that we are alive
            for x in range(10):
                if self.is_alive():
                    break
                else:
                    time.sleep(0.1)
            else:
                raise ValueError(f"Could not connect to the server after booting. Boot log:\n\n{start_status['stderr']}")

            if not self.quiet:
                self.logger("PostgreSQL successfully started in a background process, current_status:\n")
                start_status = self._run([
                    shutil.which("pg_ctl"),
                    "-D", str(self.config.database_path),
                    "status"]) # yapf: disable

        return True

    def shutdown(self) -> Any:
        """Shutsdown the current postgres instance.

        """

        self._check_psql()

        ret = self.pg_ctl(["stop"])
        return ret

    def initialize(self):
        """Initializes and starts the current postgres instance.
        """

        self._check_psql()

        if not self.quiet:
            self.logger("Initializing the database:")

        # Initialize the database
        init_status = self._run([shutil.which("initdb"), "-D", self.config.database_path])
        if "Success." not in init_status["stdout"]:
            raise ValueError(f"Could not initialize the PostgreSQL server. Error below:\n\n{init_status['stderr']}")

        # Change any configurations
        psql_conf_file = (self.config.database_path / "postgresql.conf")
        psql_conf = psql_conf_file.read_text()
        if self.config.database.port != 5432:
            assert "#port = 5432" in psql_conf
            psql_conf = psql_conf.replace("#port = 5432", f"port = {self.config.database.port}")

            psql_conf_file.write_text(psql_conf)

        # Start the database
        self.start()

        # Create the user and database
        if not self.quiet:
            self.logger(f"Building user information.")
        self._run([shutil.which("createdb"), "-p", str(self.config.database.port)])

        success = self.create_database(self.config.database.default_database)

        if success is False:
            self.shutdown()
            raise ValueError("Database created successfully, but could not connect. Shutting down postgres.")

        if not self.quiet:
            self.logger("\nDatabase successfully started!")


class TemporaryPostgres:
    def __init__(self,
                 database_name: Optional[str] = None,
                 tmpdir: Optional[str] = None,
                 quiet: bool = True,
                 logger: 'print' = print):
        """A PostgreSQL instance run in a temporary folder.

        ! Warning ! All data is lost when this object is deleted.

        Parameters
        ----------
        database_name : Optional[str], optional
            The database name to create.
        tmpdir : Optional[str], optional
            A directory to create the postgres instance in, if not None the data is not deleted upon shutdown.
        quiet : bool, optional
            If True, does not log any operations
        logger : print, optional
            The logger to show the operations to.
        """

        self._active = True

        if not tmpdir:
            self._db_tmpdir = tempfile.TemporaryDirectory()
        else:
            self._db_tmpdir = tmpdir

        self.quiet = quiet
        self.logger = logger

        config_data = {"port": find_port(), "directory": self._db_tmpdir.name}
        if database_name:
            config_data["default_database"] = database_name
        self.config = FractalConfig(database=config_data)
        self.psql = PostgresHarness(self.config)
        self.psql.initialize()

        atexit.register(self.stop)

    def __del__(self):
        """
        Cleans up the TemporaryPostgres instance on delete.
        """

        self.stop()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
        return False

    def database_uri(self, safe: bool = True, database: Optional[str] = None) -> str:
        """Provides the full Postgres URI string.

        Parameters
        ----------
        safe : bool, optional
            If True, hides the postgres password.
        database : Optional[str], optional
            An optional database to add to the string.

        Returns
        -------
        str
            The database URI
        """
        return self.config.database_uri(safe=safe, database=database)

    def stop(self) -> None:
        """
        Shuts down the Snowflake instance. This instance is not recoverable after a stop call.
        """

        if not self._active:
            return

        self.psql.shutdown()

        # Closed down
        self._active = False
        atexit.unregister(self.stop)


# createuser [-p 5433] --superuser postgres
# psql [-p 5433] -c "create database qcarchivedb;" -U postgres
# psql [-p 5433] -c "create user qcarchive with password 'mypass';" -U postgres
# psql [-p 5433] -c "grant all privileges on database qcarchivedb to qcarchive;" -U postgres