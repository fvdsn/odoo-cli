# odoo-bin specification from Odoo source

This document summarizes the behavior of `odoo-bin` as implemented in the local
Odoo checkout at:

- source: `/Users/fred/Code/Odoo/workspace/odoo`
- branch: `master`
- commit: `af49dbe8ccfb`
- release file version at analysis time: `19.4a1`

The goal is to make the current Odoo command-line surface explicit before
moving more `odoo-cli` wrapper behavior into Odoo itself.

## Source Map

- `odoo-bin` and packaged script `setup/odoo`: tiny wrappers that import
  `odoo.cli` and call `odoo.cli.main()`.
- `odoo/cli/command.py`: command dispatch, command discovery, and command base
  class.
- `odoo/cli/*.py`: built-in command modules.
- `odoo/tools/config.py`: shared server/config parser, config-file loading,
  environment-variable loading, option validation, defaults, and logging setup.
- `setup.py`: installs the `setup/odoo` script; there is no console-script entry
  point. The installed script and `odoo-bin` have the same entrypoint logic.

## Invocation Model

Canonical usage:

```bash
odoo-bin [--addons-path=PATH,...] <command> [...]
odoo-bin [server options]              # implicit server command
odoo-bin server [server options]       # explicit server command
odoo-bin --help                        # help command
```

Dispatch behavior:

- `odoo.cli.main()` receives `sys.argv[1:]`.
- If the first argument is exactly a leading `--addons-path=...` and the next
  argument is a non-option command name, Odoo pre-parses only that addons path.
  This exists so addon-provided commands can be discovered before the chosen
  command is imported.
- If the first remaining argument is a non-option, it is the command name.
- If no command name is present and `-h` or `--help` is present, Odoo runs the
  `help` command.
- Otherwise Odoo runs the default `server` command.
- Unknown command names exit with an error and suggest `odoo-bin --help`.

Command discovery:

- Built-in commands are Python modules under `odoo/cli`.
- A command class registers itself by subclassing `Command`.
- The default command name is the lowercase class name. If a class sets `name`,
  the name must match both `^[a-z][a-z0-9_]*$` and the module filename.
- Odoo first looks for already-loaded built-ins, then imports
  `odoo.cli.<command>`, then scans addon paths for `*/cli/<command>.py`.
- Addon CLI files are loaded as `odoo.cli.<command>` without importing the
  addon package itself.
- `odoo-bin --help` imports all built-in commands and scans all addon paths for
  addon commands.

Built-in commands in this checkout:

- `cloc`
- `db`
- `deploy`
- `duplicate`
- `help`
- `i18n`
- `module`
- `neutralize`
- `obfuscate`
- `scaffold`
- `server`
- `shell`
- `start`
- `upgrade_code`

## Configuration Sources

The shared parser in `odoo/tools/config.py` stores options in this effective
precedence order:

1. runtime overrides computed by Odoo after parsing
2. command-line options
3. environment variables
4. config file values from `[options]`
5. hardcoded defaults

Important parse rules:

- `parse_config(args, setup_logging=True)` parses the config file, environment,
  and CLI arguments, initializes logging unless disabled, then initializes the
  addons import path.
- Unknown CLI arguments are rejected by the server/config parser.
- `-c/--config` points to an alternate config file. If the selected file is not
  readable, parsing fails unless `-s/--save` is also set.
- `-s/--save` writes the effective exportable config to the selected config
  file, creating parent directories and setting mode `0600` for a new file.
- Config files use a raw `configparser` `[options]` section. Unknown options are
  preserved as strings and logged as warnings.
- Most path values are normalized by expanding env vars, `~`, relative paths,
  symlinks, and case.
- Boolean strings accepted from env/config include `1`, `yes`, `true`, `on`,
  `0`, `no`, `false`, and `off`.
- Comma options strip whitespace and ignore empty items.
- `--without-demo` stores the inverse into `with_demo`.

Default config-file resolution:

- First look for the appdirs user config file:
  `appdirs.user_config_dir("Odoo", "OpenERP S.A.") / "odoo.conf"`.
- On Unix this is normally `$XDG_CONFIG_HOME/Odoo/odoo.conf`, defaulting to
  `~/.config/Odoo/odoo.conf`.
- On macOS, Odoo's appdirs implementation uses the user data directory for
  config, normally under `~/Library/Application Support/Odoo/odoo.conf`.
- On Windows, if no appdirs config exists, Odoo also checks an `odoo.conf`
  alongside the executable.
- Then it checks `~/.odoorc`.
- Then it checks deprecated `~/.openerp_serverrc` and warns.
- Otherwise the default path is the appdirs user config file.
- `ODOO_RC` overrides the selected config path through the normal environment
  option mechanism.
- `OPENERP_SERVER` is recognized only to emit a deprecation warning saying to
  use `ODOO_RC`; it is not loaded as a config path.

This matters for `odoo-cli`: passing `-c <shared odoo.conf>` explicitly is the
only way to avoid `ODOO_RC` / `~/.odoorc` / appdirs mismatch surprises.

## Environment Variables

For options that are file-loadable and have no explicit environment name, Odoo
generates `ODOO_<DEST_UPPERCASE>`. For example, `http_port` becomes
`ODOO_HTTP_PORT`.

Explicit environment variable mappings:

| Environment variable | Option |
| --- | --- |
| `ODOO_RC` | `config` / `-c` |
| `PGDATABASE` | `db_name` / `-d` |
| `PGUSER` | `db_user` / `-r` |
| `PGPASSWORD` | `db_password` / `-w` |
| `PGPATH` | `pg_path` |
| `PGHOST` | `db_host` |
| `PGHOST_REPLICA` | `db_replica_host` |
| `PGPORT` | `db_port` |
| `PGPORT_REPLICA` | `db_replica_port` |
| `PGSSLMODE` | `db_sslmode` |
| `PGAPPNAME` | `db_app_name` |
| `PGDATABASE_TEMPLATE` | `db_template` |
| `PGDATABASE_SYSTEM` | `db_system` |
| `ODOO_DEV` | `dev_mode` / `--dev` |

Generated `ODOO_*` environment variables include:

- `ODOO_ADMIN_PASSWD`
- `ODOO_BIN_PATH`
- `ODOO_CSV_INTERNAL_SEP`
- `ODOO_DEFAULT_PRODUCTIVITY_APPS`
- `ODOO_IMPORT_FILE_MAXBYTES`
- `ODOO_IMPORT_FILE_TIMEOUT`
- `ODOO_IMPORT_URL_REGEX`
- `ODOO_PROXY_ACCESS_TOKEN`
- `ODOO_PUBLISHER_WARRANTY_URL`
- `ODOO_REPORTGZ`
- `ODOO_WEBSOCKET_KEEP_ALIVE_TIMEOUT`
- `ODOO_WEBSOCKET_RATE_LIMIT_BURST`
- `ODOO_WEBSOCKET_RATE_LIMIT_DELAY`
- `ODOO_WITH_DEMO`
- `ODOO_SKIP_AUTO_INSTALL`
- `ODOO_PIDFILE`
- `ODOO_ADDONS_PATH`
- `ODOO_UPGRADE_PATH`
- `ODOO_PRE_UPGRADE_SCRIPTS`
- `ODOO_SERVER_WIDE_MODULES`
- `ODOO_DATA_DIR`
- `ODOO_UNSAFE_POLICY`
- `ODOO_HTTP_INTERFACE`
- `ODOO_HTTP_PORT`
- `ODOO_GEVENT_PORT`
- `ODOO_HTTP_ENABLE`
- `ODOO_PROXY_MODE`
- `ODOO_X_SENDFILE`
- `ODOO_DBFILTER`
- `ODOO_SCREENCASTS`
- `ODOO_SCREENSHOTS`
- `ODOO_LOGFILE`
- `ODOO_SYSLOG`
- `ODOO_LOG_HANDLER`
- `ODOO_LOG_DB`
- `ODOO_LOG_DB_LEVEL`
- `ODOO_LOG_LEVEL`
- `ODOO_EMAIL_FROM`
- `ODOO_FROM_FILTER`
- `ODOO_SMTP_SERVER`
- `ODOO_SMTP_PORT`
- `ODOO_SMTP_SSL`
- `ODOO_SMTP_USER`
- `ODOO_SMTP_PASSWORD`
- `ODOO_SMTP_SSL_CERTIFICATE_FILENAME`
- `ODOO_SMTP_SSL_PRIVATE_KEY_FILENAME`
- `ODOO_DB_MAXCONN`
- `ODOO_DB_MAXCONN_GEVENT`
- `ODOO_LOAD_LANGUAGE`
- `ODOO_OVERWRITE_EXISTING_TRANSLATIONS`
- `ODOO_LIST_DB`
- `ODOO_OSV_MEMORY_COUNT_LIMIT`
- `ODOO_TRANSIENT_AGE_LIMIT`
- `ODOO_MAX_CRON_THREADS`
- `ODOO_LIMIT_TIME_WORKER_CRON`
- `ODOO_UNACCENT`
- `ODOO_GEOIP_CITY_DB`
- `ODOO_GEOIP_COUNTRY_DB`
- `ODOO_WORKERS`
- `ODOO_GEVENT_WORKERS`
- `ODOO_LIMIT_MEMORY_SOFT`
- `ODOO_LIMIT_MEMORY_SOFT_GEVENT`
- `ODOO_LIMIT_MEMORY_HARD`
- `ODOO_LIMIT_MEMORY_HARD_GEVENT`
- `ODOO_LIMIT_TIME_CPU`
- `ODOO_LIMIT_TIME_REAL`
- `ODOO_LIMIT_TIME_REAL_CRON`
- `ODOO_LIMIT_REQUEST`

Other environment variables that influence `odoo-bin` or commands:

| Environment variable | Effect |
| --- | --- |
| `NO_COLOR` | disables all Odoo log color categories |
| `FORCE_COLOR` | enables all Odoo log color categories |
| `ODOO_PY_COLORS` | sets all color categories; accepted values are `always`, `never`, `auto`, or a boolean string |
| `LISTEN_FDS`, `LISTEN_PID` | enable systemd-style HTTP socket activation when `LISTEN_FDS=1` and `LISTEN_PID` matches the process |
| `ODOO_MAX_HTTP_THREADS` | positive integer for HTTP thread pool size; defaults to `2 * os.cpu_count() + 1` |
| `PYTHONSTARTUP` | script run by `odoo-bin shell` unless `--shell-file` is set |
| `VIRTUAL_ENV` | `odoo-bin start` uses this as `--path` when `--path` is omitted and the default `.` is still active |
| `ODOO_HTTP_SOCKET_FD` | internal/reload socket handoff for the HTTP server |
| `ODOO_READY_SIGHUP_PID` | internal signal hook used after reload child readiness |
| `ODOO_RELOAD_CHILD` | marks a reload child process |
| `DEBUGPY_RUNNING` | changes reload behavior under debugpy |
| `ODOO_HTTP_SOCKET_TIMEOUT` | controls HTTP socket timeout |
| `ODOO_PROFILE_PRELOAD` | profiles registry preload |
| `ODOO_PROFILE_PRELOAD_INTERVAL` | sampling interval for preload profiling |
| `ODOO_PROFILE_PRELOAD_SQL` | includes SQL collector in preload profiling |
| `ODOO_TEST_MAX_FAILED_TESTS` | stops test execution after this many failures |
| `ODOO_TEST_FAILURE_RETRIES` | controls test retry count |
| `ODOO_TEST_DISABLE_TIMEOUT` | disables Odoo test timeouts |
| `ODOO_FAKETIME_TEST_MODE` | alters SQL/db behavior for fake-time tests |
| `ODOO_RUNBOT`, `ODOO_TEST` | make database serial generation random |
| `ODOO_BROWSER_BIN` | browser binary used by browser tests |
| `ODOO_BROWSER_LOG_VERBOSITY` | browser test log verbosity |
| `ODOO_BROWSER_CPU_THROTTLING` | browser test CPU throttling |
| `ODOO_LIMIT_LITEVAL_BUFFER` | limit for monkeypatched literal evaluation buffer |
| `ODOO_SKIP_GC_SESSIONS` | skips HTTP session garbage collection in relevant code paths |
| `XDG_CONFIG_HOME` | affects default config path on Unix |
| `XDG_CONFIG_DIRS` | affects site config path |
| `XDG_DATA_HOME` | affects default data path on Unix |
| `XDG_DATA_DIRS` | affects site data path |

## Server And Shared Config Options

These options are parsed by the `server` command and by commands that call
`config.parse_config()` directly. Some argparse-based commands expose only a
small subset and translate those values into config options.

### File-Only Options

These can be loaded from config/env but are not accepted as server CLI flags:

| Config key | Default | Notes |
| --- | --- | --- |
| `admin_passwd` | `admin` | super-admin password/hash |
| `bin_path` | empty | path, not exported by `--save` |
| `csv_internal_sep` | `,` | CSV separator |
| `default_productivity_apps` | `False` | bool, not exported |
| `import_file_maxbytes` | `10485760` | int, not exported |
| `import_file_timeout` | `3` | int, not exported |
| `import_url_regex` | `^(?:http\|https)://` | not exported |
| `proxy_access_token` | empty | not exported |
| `publisher_warranty_url` | `http://services.odoo.com/publisher-warranty/` | not exported |
| `reportgz` | `False` | bool |
| `websocket_keep_alive_timeout` | `3600` | int |
| `websocket_rate_limit_burst` | `10` | int |
| `websocket_rate_limit_delay` | `0.2` | float |

### Common Options

| CLI option | Config key | Default | Notes |
| --- | --- | --- | --- |
| `-c`, `--config PATH` | `config` | resolved config path | not file-loadable; env `ODOO_RC` |
| `-s`, `--save` | `save` | `False` | writes effective config |
| `-i`, `--init MODULE,...` | `init` | empty list | install modules, requires `-d`; `all` means all modules |
| `-u`, `--update MODULE,...` | `update` | empty list | update modules, requires `-d`; `all` becomes update `base` |
| `--reinit MODULE,...` | `reinit` | empty list | reinitialize modules, requires `-d` |
| `--with-demo` | `with_demo` | `False` | install demo data in new databases |
| `--without-demo[=BOOL]` | `with_demo` | inverse | optional value; no value means no demo |
| `--skip-auto-install` | `skip_auto_install` | `False` | skip auto-install modules |
| `-P`, `--import-partial PATH` | `import_partial` | empty | big import resume state |
| `--pidfile PATH` | `pidfile` | empty | server writes/removes pid file outside evented mode |
| `--addons-path PATH,...` | `addons_path` | empty list | validates addon directories and glob expansions |
| `--upgrade-path PATH,...` | `upgrade_path` | empty list | validates upgrade script layout |
| `--pre-upgrade-scripts PATH,...` | `pre_upgrade_scripts` | empty list | validates files |
| `--load MODULE,...` | `server_wide_modules` | `base,rpc,web` | runtime ensures at least `base` and `web` |
| `-D`, `--data-dir PATH` | `data_dir` | appdirs user data dir | filestore, sessions, generated addons |
| `--unsafe-policy disable\|log\|raise\|terminate` | `unsafe_policy` | `log` | unsafe object policy |

### HTTP And Web Options

| CLI option | Config key | Default | Notes |
| --- | --- | --- | --- |
| `--http-interface ADDRESS` | `http_interface` | `127.0.0.1` | empty value is reset to `127.0.0.1` at runtime |
| `-p`, `--http-port PORT` | `http_port` | `8069` | int |
| `--gevent-port PORT` | `gevent_port` | `8072` | int |
| `--no-http` | `http_enable` | `True` | stores `False` |
| `--proxy-mode` | `proxy_mode` | `False` | enables trusted reverse proxy wrappers |
| `--x-sendfile` | `x_sendfile` | `False` | enables `X-Sendfile`/`X-Accel-Redirect` |
| `--db-filter REGEXP` | `dbfilter` | empty | `%d` domain and `%h` host placeholders |

### Testing Options

| CLI option | Config key | Default | Notes |
| --- | --- | --- | --- |
| `--test-file PATH` | `test_file` | empty | converted to `--test-tags` when a Python file exists |
| `--test-enable` | `test_enable` | `False` | implies `--stop-after-init` |
| `-t`, `--test-tags SPECS` | `test_tags` | empty | comma-separated include/exclude specs |
| `--screencasts DIR` | `screencasts` | empty | output under `DIR/{db}/screencasts` |
| `--screenshots DIR` | `screenshots` | temp `odoo_tests` dir | output under `DIR/{db}/screenshots` |

Post-processing:

- `--test-file` appends the absolute file path to `test_tags` and enables
  tests.
- `--test-enable` without tags sets `test_tags` to `+standard`.
- Any active test tags set `test_enable=True` and `stop_after_init=True`.
- If tests are enabled with no database, Odoo logs a warning that tests will not
  run.

### Logging Options

| CLI option | Config key | Default | Notes |
| --- | --- | --- | --- |
| `--logfile PATH` | `logfile` | empty | mutually exclusive with `--syslog` |
| `--syslog` | `syslog` | `False` | mutually exclusive with `--logfile` |
| `--log-handler MODULE:LEVEL` | `log_handler` | `:INFO` | repeatable, comma type |
| `--log-web` | `log_handler` | append `odoo.http:DEBUG` | shortcut |
| `--log-sql` | `log_handler` | append `odoo.sql_db:DEBUG` | shortcut |
| `--log-db DB` | `log_db` | empty | logging database |
| `--log-db-level LEVEL` | `log_db_level` | `warning` | database logging level |
| `--log-level LEVEL` | `log_level` | `info` | one of `info`, `debug_rpc`, `warn`, `test`, `critical`, `runbot`, `debug_sql`, `error`, `debug`, `debug_rpc_answer`, `notset` |

Log handlers from defaults, config, env, and CLI are accumulated and
deduplicated by logger name, with the last value for a logger winning.

### SMTP Options

| CLI option | Config key | Default |
| --- | --- | --- |
| `--email-from EMAIL` | `email_from` | empty |
| `--from-filter REGEXP` | `from_filter` | empty |
| `--smtp HOST` | `smtp_server` | `localhost` |
| `--smtp-port PORT` | `smtp_port` | `25` |
| `--smtp-ssl` | `smtp_ssl` | `False` |
| `--smtp-user USER` | `smtp_user` | empty |
| `--smtp-password PASSWORD` | `smtp_password` | empty |
| `--smtp-ssl-certificate-filename PATH` | `smtp_ssl_certificate_filename` | empty |
| `--smtp-ssl-private-key-filename PATH` | `smtp_ssl_private_key_filename` | empty |

### Database Options

| CLI option | Config key | Default | Env |
| --- | --- | --- | --- |
| `-d`, `--database DATABASE,...` | `db_name` | empty list | `PGDATABASE` |
| `-r`, `--db_user USER` | `db_user` | empty | `PGUSER` |
| `-w`, `--db_password PASSWORD` | `db_password` | empty | `PGPASSWORD` |
| `--pg_path PATH` | `pg_path` | empty | `PGPATH` |
| `--db_host HOST` | `db_host` | empty | `PGHOST` |
| `--db_replica_host HOST` | `db_replica_host` | `None` | `PGHOST_REPLICA` |
| `--db_port PORT` | `db_port` | `None` | `PGPORT` |
| `--db_replica_port PORT` | `db_replica_port` | `None` | `PGPORT_REPLICA` |
| `--db_sslmode MODE` | `db_sslmode` | `prefer` | `PGSSLMODE` |
| `--db_app_name NAME` | `db_app_name` | `odoo-{pid}` | `PGAPPNAME` |
| `--db_maxconn N` | `db_maxconn` | `64` | `ODOO_DB_MAXCONN` |
| `--db_maxconn_gevent N` | `db_maxconn_gevent` | `None` | `ODOO_DB_MAXCONN_GEVENT` |
| `--db-template DB` | `db_template` | `template0` | `PGDATABASE_TEMPLATE` |
| `--db-system DB` | `db_system` | `postgres` | `PGDATABASE_SYSTEM` |

`db_sslmode` choices are `disable`, `allow`, `prefer`, `require`, `verify-ca`,
and `verify-full`.

The `server` command refuses to run when the effective DB user is `postgres`.
It checks `config['db_user']` first, then `PGUSER`.

### Internationalization Options

| CLI option | Config key | Default | Notes |
| --- | --- | --- | --- |
| `--load-language LANGS` | `load_language` | unset | load translations; `-d` required |
| `--i18n-overwrite` | `overwrite_existing_translations` | `False` | requires `-u/--update` |

### Security And Advanced Options

| CLI option | Config key | Default | Notes |
| --- | --- | --- | --- |
| `--no-database-list` | `list_db` | `True` | stores `False` |
| `--dev FEATURE,...` | `dev_mode` | empty list | env `ODOO_DEV`; `all` expands to `access,qweb,reload,xml` plus the literal `all` |
| `--stop`, `--stop-after-init` | `stop_after_init` | `False` | not config/env loadable |
| `--osv-memory-count-limit N` | `osv_memory_count_limit` | `0` | int |
| `--transient-age-limit HOURS` | `transient_age_limit` | `1.0` | float |
| `--max-cron-threads N` | `max_cron_threads` | `2` | int |
| `--limit-time-worker-cron SECONDS` | `limit_time_worker_cron` | `0` | 0 disables |
| `--unaccent` | `unaccent` | `False` | try enabling PostgreSQL unaccent extension |
| `--geoip-city-db PATH`, `--geoip-db PATH` | `geoip_city_db` | `/usr/share/GeoIP/GeoLite2-City.mmdb` | path |
| `--geoip-country-db PATH` | `geoip_country_db` | `/usr/share/GeoIP/GeoLite2-Country.mmdb` | path |

Dev features listed in help:

- `access`: log access-error tracebacks
- `qweb`: log compiled XML with QWeb errors
- `reload`: restart server on source-code change
- `replica`: simulate readonly replica deployment
- `werkzeug`: open HTML debugger on HTTP request error
- `xml`: read views from source instead of database

### Multiprocessing Options

| CLI option | Config key | Default | Notes |
| --- | --- | --- | --- |
| `--workers N` | `workers` | `0` | POSIX only; 0 disables prefork |
| `--gevent-workers N` | `gevent_workers` | `1` | POSIX only |
| `--limit-memory-soft BYTES` | `limit_memory_soft` | `2147483648` | 2048 MiB |
| `--limit-memory-soft-gevent BYTES` | `limit_memory_soft_gevent` | `None` | POSIX only; defaults to soft worker limit |
| `--limit-memory-hard BYTES` | `limit_memory_hard` | `2684354560` | POSIX only; 2560 MiB |
| `--limit-memory-hard-gevent BYTES` | `limit_memory_hard_gevent` | `None` | POSIX only; defaults to hard worker limit |
| `--limit-time-cpu SECONDS` | `limit_time_cpu` | `60` | POSIX only |
| `--limit-time-real SECONDS` | `limit_time_real` | `120` | int |
| `--limit-time-real-cron SECONDS` | `limit_time_real_cron` | `-1` | default means use `--limit-time-real`; 0 disables |
| `--limit-request N` | `limit_request` | `65536` | POSIX only |

On non-POSIX platforms, `PosixOnlyOption` hides these options from CLI help and
marks them non-loadable/non-exportable.

## Command: help

Usage:

```bash
odoo-bin --help
odoo-bin help
```

Behavior:

- Loads all built-in commands.
- Scans addon paths for addon-provided commands.
- Prints:
  `usage: odoo-bin [--addons-path=PATH,...] <command> [...]`
- Lists command names and the first-line docstring for each registered command.
- Suggests `odoo-bin server --help` for regular server options and
  `odoo-bin <command> --help` for command-specific options.

## Command: server

Usage:

```bash
odoo-bin [server options]
odoo-bin server [server options]
```

Description: start the Odoo server. This is the default command.

Arguments:

- all shared server/config options from `odoo/tools/config.py`.

Behavior:

- Warns on stderr if running as root on POSIX.
- Parses config and initializes logging.
- Aborts if the effective database user is `postgres`.
- Logs Odoo version, config file path if readable, addons paths, upgrade path,
  pre-upgrade scripts, and database connection target.
- Warns if running on a Python minor version newer than
  `odoo.release.MAX_PY_VERSION`.
- For each database in `db_name`, attempts to create an empty database. If it
  creates one, it sets `init['base'] = True`. Existing DBs are ignored.
- Writes `pidfile` when configured and not running evented, then removes it at
  exit from the main process.
- Calls `odoo.service.server.start(preload=config['db_name'], stop=stop)`.
- Exits with the return code from `server.start()`.

Notable implications:

- Passing `-i base --stop-after-init --no-http -d <db>` initializes an empty
  database and exits.
- Passing no `-i`/`-u` for a newly created database creates the DB shell, but
  the `base` initialization path depends on server startup/preload behavior.

## Command: start

Usage:

```bash
odoo-bin start [--path PATH] [-d DATABASE] [server options]
```

Description: quickly start the Odoo server with default project options.

Arguments:

| Option | Default | Notes |
| --- | --- | --- |
| `--path PATH` | `.` | directory where project modules are stored; help says autodetect from current dir |
| `-d`, `--database DATABASE` | unset | database name; defaults to module/project directory name |
| other args | forwarded | parsed later by the `server` command after start rewrites args |

Behavior:

- Parses known `start` options and leaves unknown options for server parsing.
- If `--path` is omitted and `VIRTUAL_ENV` is set, uses `VIRTUAL_ENV` as the
  project path.
- Expands and absolutizes the project path.
- If the path is inside an Odoo module, uses that module name as the default
  database and changes project path to the module's parent directory.
- Scans the project path for addon manifests. If it finds modules and
  `--addons-path` is not already present in the raw command args, appends
  `--addons-path=<project_path>`.
- If no database was provided, defaults to the detected module name or the
  project directory basename and appends `-d <database>`.
- Attempts to create the database. If created, sets `config['init']['base'] =
  True`; if it exists, continues.
- If `--db-filter` is not already present, appends `--db-filter=^<database>$`.
- Removes `--path` and its value before forwarding to `server.main()`.
- Also removes raw `-p` and its following value, even though `start` does not
  define `-p`; this means `odoo-bin start -p 8070` is consumed as if it were a
  path option rather than reaching the server as `--http-port`.

## Command: shell

Usage:

```bash
odoo-bin shell [server options] [--shell-file FILE] [--shell-interface NAME]
```

Description: start Odoo in an interactive Python shell.

Additional arguments:

| Option | Notes |
| --- | --- |
| `--shell-file FILE` | run a Python script after shell startup; overrides `PYTHONSTARTUP` |
| `--shell-interface NAME` | preferred REPL: `ipython`, `ptpython`, `bpython`, or `python` |

Behavior:

- Adds shell options to the shared config parser, parses full server config, and
  initializes logging.
- Reports the server configuration.
- Calls `server.start(preload=[], stop=True)` to initialize enough server state
  without starting a long-running server.
- Installs a SIGINT handler that raises `KeyboardInterrupt`.
- Requires zero or one database in `db_name`; exits if multiple DBs are given.
- If a database is provided:
  - opens `Registry(dbname)`
  - creates an environment as `SUPERUSER_ID`
  - exposes `env` and `self = env.user`
  - rolls back before and after the shell session
- If no database is provided:
  - exposes only `openerp` and `odoo`
  - prints a hint to use `shell -d dbname`
- If stdin is not a TTY, executes stdin as Python with the shell locals and
  `__name__ = "__main__"`.
- Otherwise prints local variables and tries REPLs in order:
  `ipython`, `ptpython`, `bpython`, `python`, unless
  `--shell-interface` is set, in which case it tries that REPL then `python`.

## Command: module

Usage:

```bash
odoo-bin module install [common module args] MODULE...
odoo-bin module upgrade [common module args] [--outdated] MODULE...
odoo-bin module uninstall [common module args] MODULE...
odoo-bin module force-demo [common module args]
```

Description: manage modules and install demo data.

Common module arguments:

| Option | Notes |
| --- | --- |
| `-c`, `--config FILE` | specific config file |
| `-d`, `--database DATABASE` | database name; connection details come from config |
| `-D`, `--data-dir DIR` | Odoo data directory |

The command translates common args to config args and always adds `--no-http`.
After config parsing it requires exactly one effective database, whether from
CLI, env, or config.

### module install

Arguments:

- `MODULE...`: module names to install. A `.zip` file path can be supplied for
  data-module import.

Behavior:

- Initializes the addons import path before starting DB work.
- Filters requested names to modules that exist on disk or zip files that
  exist.
- Opens a registry environment on the target database.
- Calls `ir.module.module.update_list()`.
- Installs matching modules with `button_immediate_install()`.
- For non-installable arguments that are zip files:
  - if the DB does not have an `imported` field on `ir.module.module`, logs a
    warning that `base_import_module` is required.
  - otherwise imports each zip with `_import_zipfile()`.

### module upgrade

Arguments:

- `MODULE...`: modules to upgrade. Use `base` or `all` for everything.
- `--outdated`: intended help text says to update only modules with a newer
  version on disk.

Behavior:

- If `all` is present, selects all installed modules.
- Otherwise filters requested names to valid module names on disk and searches
  module records by name.
- If `--outdated` is set, the code currently keeps modules where
  `parse_version(installed_version) > parse_version(latest_version)`.
- Calls `button_immediate_upgrade()` on the resulting recordset if non-empty.

### module uninstall

Arguments:

- `MODULE...`: module names to uninstall.

Behavior:

- Searches `ir.module.module` by provided names.
- Calls `button_immediate_uninstall()` if any records are found.

### module force-demo

Arguments: common module args only.

Behavior:

- Opens the target DB environment and calls `odoo.modules.loading.force_demo()`.

## Command: db

Usage:

```bash
odoo-bin db [db-global options] <subcommand> [...]
```

Description: command-line version of the database manager. Commands are
filestore-aware.

DB-global options:

| Option | Notes |
| --- | --- |
| `-c`, `--config FILE` | passed to config parser |
| `-D`, `--data-dir DIR` | passed as `--data-dir` |
| `--addons-path PATH,...` | passed as `--addons-path` |
| `-r`, `--db_user USER` | passed as `--db_user` |
| `-w`, `--db_password PASSWORD` | passed as `--db_password` |
| `--pg_path PATH` | passed as `--pg_path` |
| `--db_host HOST` | passed as `--db_host` |
| `--db_port PORT` | passed as `--db_port` |
| `--db_sslmode MODE` | passed as `--db_sslmode` |

After parsing, the command builds config args only from non-`None` global
values, initializes logging, reports configuration, then dispatches.

If a subcommand would create/copy/rename into a target database that already
exists, it exits unless `--force`/`-f` was set. With force, it drops the existing
target first.

### db init

Usage:

```bash
odoo-bin db init DATABASE [--with-demo] [--force] [--language LANG]
                 [--username USER] [--password PASSWORD] [--country CODE]
```

Behavior:

- Creates and initializes a database with minimum required modules via
  `odoo.modules.db.create()`.
- Options:
  - `DATABASE`: database to create.
  - `--with-demo`: install demo data.
  - `--force`: drop existing database first.
  - `--language`: default language, default `en_US`.
  - `--username`: admin login, default `admin`.
  - `--password`: admin password, default `admin`.
  - `--country`: country code for the main company.

### db load

Usage:

```bash
odoo-bin db load [-f] [-n] [DATABASE] DUMP_FILE
```

Behavior:

- Restores a zip dump into a database.
- If `DATABASE` is omitted, uses the dump filename stem.
- `DUMP_FILE` may be a local path or URL.
- For URLs, fetches with `requests.get(..., timeout=10)`.
- Requires a zip file. Raw pg dumps are rejected with a message to use
  `pg_restore` or `psql`.
- Calls `db.restore(db_name, dump_file, copy=True,
  neutralize_database=<--neutralize>)`.
- Options:
  - `-f`, `--force`: drop existing target DB first.
  - `-n`, `--neutralize`: neutralize after restore.

### db dump

Usage:

```bash
odoo-bin db dump DATABASE [DUMP_PATH] [--format zip|dump] [--no-filestore]
```

Behavior:

- Dumps `DATABASE`.
- If `DUMP_PATH` is omitted or `-`, writes to stdout.
- Otherwise opens the target path in binary mode and passes it to `db.dump()`.
- Options:
  - `--format zip|dump`: output format, default `zip`.
  - `--no-filestore`: for zip dumps, omit the filestore.
- Implementation detail: when dumping to stdout, the command calls
  `db.dump(database, sys.stdout.buffer)` without passing `dump_format` or
  `filestore`, so explicit `--format`/`--no-filestore` do not affect that code
  path.

### db duplicate

Usage:

```bash
odoo-bin db duplicate [-f] [-n] SOURCE TARGET
```

Behavior:

- Duplicates database and filestore with `db.duplicate()`.
- Options:
  - `-f`, `--force`: drop existing target first.
  - `-n`, `--neutralize`: neutralize target after duplicate.

### db rename

Usage:

```bash
odoo-bin db rename [-f] SOURCE TARGET
```

Behavior:

- Renames database and filestore with `db.rename()`.
- `-f`, `--force` drops an existing target first.

### db drop

Usage:

```bash
odoo-bin db drop DATABASE
```

Behavior:

- Drops the database and filestore with `db.drop()`.

## Command: i18n

Usage:

```bash
odoo-bin i18n import [common i18n args] -l LANG [-w] FILE...
odoo-bin i18n export [common i18n args] [-l LANG...] [-o FILE] MODULE...
odoo-bin i18n loadlang [common i18n args] -l LANG...
```

Description: import, export, setup languages, and internationalization files.

Common i18n arguments:

| Option | Notes |
| --- | --- |
| `-c`, `--config FILE` | specific config file |
| `-d`, `--database DATABASE` | database name |

The command translates common args to config args, always adds `--no-http`, and
requires exactly one effective database.

Language codes must follow XPG/POSIX locale format. Help suggests querying
`res_lang.iso_code` to list available codes.

### i18n import

Arguments:

- `FILE...`: translation files. Allowed extensions: `.po`, `.csv`.
- `-l`, `--language LANG`: required language code.
- `-w`, `--overwrite`: overwrite existing terms.

Behavior:

- Deduplicates input paths while preserving order.
- Logs and ignores paths that do not exist or do not have an allowed extension.
- Errors if no valid path remains.
- Resolves language by `iso_code` or `code`; only active languages are valid.
- Uses `TranslationImporter.load()` for each file and then
  `TranslationImporter.save(overwrite=...)`.

### i18n export

Arguments:

- `MODULE...`: modules to export.
- `-l`, `--languages LANG...`: language codes, default `pot`.
- `-o`, `--output FILE`: write one combined output file instead of module i18n
  folders. Allowed extensions: `.po`, `.pot`, `.tgz`, `.csv`; `-` writes `.po`
  data to stdout.

Behavior:

- `pot` in the language list means export a template.
- With `--output`, exactly one language/template may be supplied.
- Template export to `.csv` is rejected.
- Searches requested modules and ignores not-found or not-installed modules.
- Errors if no installed module remains.
- Resolves languages by `iso_code` or `code`; inactive languages are ignored
  with a warning and install hint.
- Without `--output`, writes:
  - `<module>/i18n/<module>.pot` for templates
  - `<module>/i18n/<language.iso_code>.po` for languages
- With `--output`, writes one file for all modules.
- Uses `trans_export()`. Logs a warning if no translatable terms are found.

### i18n loadlang

Arguments:

- `-l`, `--languages LANG...`: language codes to install.

Behavior:

- Resolves languages including inactive records.
- Calls `load_language(env.cr, language.code)` for each resolved language.

## Command: cloc

Usage:

```bash
odoo-bin cloc [-d DATABASE] [-p PATH]... [-v] [server/config options]
```

Description: count relevant Python, JavaScript, and XML lines per module.

Arguments:

| Option | Notes |
| --- | --- |
| `-d`, `--database DATABASE` | count custom code installed in a database |
| `-p`, `--path PATH` | count a file or directory; repeatable |
| `-v`, `--verbose` | count verbosity; repeatable |

Behavior:

- Parses known `cloc` args and appends `--no-http` to the parse-known input.
- If neither database nor path is provided, prints help and exits.
- If database is provided:
  - rejects comma-separated multiple databases.
  - parses shared config with `-d <database>` plus unknown args.
  - calls `Cloc.count_database(config['db_name'][0])`.
- For each path, calls `Cloc.count_path(path)`.
- Prints the report with the selected verbosity.

## Command: deploy

Usage:

```bash
odoo-bin deploy PATH [URL] [--db DB] [--login LOGIN] [--password PASSWORD]
                 [--verify-ssl] [--force]
```

Description: deploy a module on an Odoo instance.

Arguments:

| Argument | Default | Notes |
| --- | --- | --- |
| `PATH` | required | module directory to zip and upload |
| `URL` | `http://localhost:8069` | server URL; if no scheme is present, `https://` is prepended |
| `--db DB` | empty | database if server does not use db-filter |
| `--login LOGIN` | `admin` | login |
| `--password PASSWORD` | `admin` | password |
| `--verify-ssl` | false | by default requests disables certificate verification |
| `--force` | false | force init even if already installed; updates `noupdate="1"` records |

Behavior:

- Prints help and exits if no args are provided.
- Zips the module directory into a temporary zip.
- Opens `/web/login?db=<db>` to set DB in the HTTP session.
- POSTs to `/base_import_module/login_upload` with `login`, `password`, `db`,
  `force`, and multipart `mod_file`.
- If response status is 404, raises a specific error saying
  `base_import_module` is missing or outdated.
- Prints the server response text.
- Removes the temporary zip in a `finally` block.

## Command: duplicate

Usage:

```bash
odoo-bin duplicate [server options] --factors FACTORS --models MODELS --sep SEP
```

Description: populate a database by duplicating existing data for testing/demo.

Additional options:

| Option | Default | Notes |
| --- | --- | --- |
| `--factors` | `10000` | comma-separated factors; last factor is reused for remaining models |
| `--models` | `res.partner,product.template,account.move,sale.order,crm.lead,stock.picking,project.task` | comma-separated model names |
| `--sep` | `_` | single-character separator for char/text fields |

Behavior:

- Adds duplicate-specific options to the shared config parser.
- Parses full config with `--no-http`.
- Converts factors to integers.
- Builds a model-to-factor mapping, reusing the last factor if fewer factors
  than models were supplied.
- Converts `--sep` to a Unicode code point and raises if it is not one
  character.
- Requires exactly one database.
- Opens an environment with `active_test=False`.
- Filters out missing, transient, and abstract models.
- Calls `odoo.tools.duplicate.duplicate_models()`, flushes all, and logs timing.

## Command: neutralize

Usage:

```bash
odoo-bin neutralize [server options] [--stdout] -d DATABASE
```

Description: neutralize a production database for testing: no emails sent, etc.

Additional option:

- `--stdout`: print neutralization SQL instead of applying it.

Behavior:

- Adds the option to the shared config parser and parses full config.
- Requires exactly one database.
- If `--stdout`:
  - opens a cursor.
  - discovers installed modules.
  - prints `BEGIN;`, all neutralization queries with semicolons, and `COMMIT;`.
- Otherwise calls `odoo.modules.neutralize.neutralize_database(cursor)`.
- On any exception, logs a critical message that the database is not neutralized
  and exits with status 1.

## Command: obfuscate

Usage:

```bash
odoo-bin obfuscate [server options] -d DATABASE --pwd PASSWORD [options]
```

Description: obfuscate data in a database.

Additional options:

| Option | Notes |
| --- | --- |
| `--pwd PASSWORD` | required; encryption/decryption password |
| `--fields table.column,...` | additional fields to obfuscate/unobfuscate |
| `--exclude table.column,...` | fields to exclude |
| `--file FILE` | file with one `table.column` per line |
| `--unobfuscate` | decrypt instead of encrypt |
| `--allfields` | unobfuscate all text/varchar/jsonb fields outside `ir_%`; only valid with `--unobfuscate` |
| `--vacuum` | vacuum tables after unobfuscating |
| `--pertablecommit` | commit after each table instead of one large transaction |
| `-y`, `--yes` | skip manual unsafe-operation confirmation |

Behavior:

- Prints shared parser help and exits if no args are provided.
- Parses full config.
- Requires `--pwd`.
- Rejects `--allfields` unless `--unobfuscate` is set.
- Requires exactly one database.
- Opens a registry cursor, starts a transaction, and creates PostgreSQL
  extension `pgcrypto` if needed.
- Stores/checks an encrypted password marker in `ir_config_parameter` key
  `odoo_cyph_pwd`.
- Starts from a built-in list of common PII-ish fields, including partner,
  mail, CRM, country, product, account, sale, stock, and project fields.
- Adds fields from `--fields` and `--file`.
- Applies `--exclude` unless `--allfields` is set.
- If `--allfields`, queries information schema for all text/varchar/jsonb
  columns outside `ir_%`.
- Validates fields exist and are text/varchar/jsonb.
- If obfuscating and `--yes` is not set, asks two confirmation questions:
  one `y/N`, then the database name in uppercase.
- For text/varchar fields, encrypts/decrypts strings with `pgp_sym_encrypt` /
  `pgp_sym_decrypt` and an `odoo_cyph_` prefix guard.
- For jsonb fields, rewrites each key value with nested `jsonb_set`.
- On unobfuscation with `--vacuum`, runs `VACUUM FULL` on processed tables.
- Clears the password marker after unobfuscation.
- Commits on success, rolls back on password-check failure, and exits with
  `ERROR: ...` on exceptions.

## Command: scaffold

Usage:

```bash
odoo-bin scaffold [-t TEMPLATE] NAME [DEST]
```

Description: generate an Odoo module skeleton.

Arguments:

| Argument | Default | Notes |
| --- | --- | --- |
| `-t`, `--template TEMPLATE` | `default` | built-in template name or path to a template directory |
| `NAME` | required | module display/name input; converted to snake case for directory |
| `DEST` | `.` | destination directory; created if missing |

Built-in templates in this checkout:

- `default`
- `theme`

Behavior:

- Prints help and exits if no args are provided.
- Template lookup first checks built-ins under `odoo/cli/templates`, then treats
  the value as a filesystem directory.
- Converts module name to snake case for the module directory.
- Recursively copies template files.
- Renders template paths and selected text file contents with Jinja2.
- Strips `.template` suffix from generated filenames.
- Creates destination directories as needed.
- Renders files with extensions `.py`, `.xml`, `.csv`, `.js`, `.rst`, `.html`,
  and `.template`; other files are copied as bytes.

## Command: upgrade_code

Usage:

```bash
odoo-bin upgrade_code (--script NAME | --from VERSION) [--to VERSION]
                      [--glob GLOB] [--dry-run]
                      [--addons-path PATH,...]
```

Description: rewrite source code using scripts found at
`odoo/upgrade_code`.

Arguments:

| Option | Default | Notes |
| --- | --- | --- |
| `--script NAME` | mutually exclusive | run one script; may match a script filename fragment |
| `--from VERSION` | mutually exclusive | run all scripts from this version, inclusive |
| `--to VERSION` | current Odoo release version | run scripts until this version, inclusive |
| `--glob GLOB` | `**/*` | select files to rewrite |
| `--dry-run` | false | list files that would change but do not write |
| `--addons-path PATH,...` | current config addons path | additional addons paths |

Behavior:

- Can run through `odoo-bin` or directly as `python odoo/cli/upgrade_code.py`.
- When running through Odoo:
  - parses `--addons-path` with Odoo's addons-path validator.
  - sets `config['addons_path']`.
  - initializes `odoo.addons.__path__`.
- When standalone:
  - uses a simplified parser.
  - requires `--addons-path`.
- Collects files under each addon path matching `--glob`, excluding
  `__pycache__`, limited to suffixes `.py`, `.js`, `.css`, `.scss`, `.xml`,
  `.csv`, `.po`, `.pot`.
- A migration script exposes `upgrade(file_manager)`.
- If `--script` is provided:
  - resolves an exact path or a single script in `odoo/upgrade_code` matching
    the fragment.
  - prevents escaping above `odoo/upgrade_code`.
- Otherwise selects scripts whose parsed version is between `--from` and
  `--to`, inclusive.
- Runs selected scripts in sorted order.
- Prints paths of dirty files.
- Writes changed files unless `--dry-run` is set.
- Prints a summary on TTY.
- Exits `1` if any file was dirty, otherwise `0`.

Upgrade scripts present in this checkout:

- `17.5-00-example.py`
- `17.5-01-tree-to-list.py`
- `18.1-00-sql-constraint.py`
- `18.1-02-route-jsonrpc.py`
- `18.2-00-l10n-translate.py`
- `18.3-00-l10n-fiscal-position-taxes.py`
- `18.5-00-deprecated-properties.py`
- `18.5-00-domain-dynamic-dates.py`
- `18.5-00-no-tax-tag-invert.py`
- `19.1-00-t-call.py`
- `19.3-00-account-groups.py`
- `19.3-00-account-report-foldable.py`
- `19.3-00-base64-in-xml.py`
- `19.4-00-ormcache-on-transaction.py`
- `owl3-migration.py`
- `tools_etree.py`
- `tools_js_expressions.py`

## Current odoo-cli Migration Relevance

Current native Odoo master already has:

- `odoo-bin db init` for creating and initializing a database.
- `odoo-bin db dump/load/duplicate/rename/drop` with filestore awareness.
- `odoo-bin module install/upgrade/uninstall/force-demo`.
- `odoo-bin shell`.
- `odoo-bin start`, but its conventions are project/module-directory oriented,
  not the `odoo-cli` workspace/worktree conventions.

Still owned by `odoo-cli` in the current design:

- workspace resolution (`ODOO_DIR`, single workspace, no parent walking)
- repository cloning/enabling and git worktree management
- venv creation and Odoo-version detection
- worktree target resolution
- database naming derived from worktree/target
- addons path discovery and ordering across worktree repos
- port allocation and `.run/{worktree}/{db}/ports`
- passing the shared config path explicitly
- per-instance command assembly for older Odoo versions

Candidates for upstreaming into Odoo/`odoo-bin`:

- a `start` convention that can derive database, addons path, dev defaults, and
  ports in the same way as `odoo-cli`, without depending on a wrapper-specific
  workspace.
- a `test` command that owns common test database/module/tag conventions.
- config initialization (`odoo-bin config init`) so Odoo owns config-file
  location and format creation.
- an introspection/report command for the fully resolved effective config and
  runtime server URL/ports, so wrappers can read Odoo-owned state instead of
  duplicating it.
