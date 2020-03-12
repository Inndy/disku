# DISKU - disk usage monitor utility

This is a server/client based utility to monitor disk usage

## Requirements

`python3 -m pip install -r requirements.txt` (you may need to use `sudo -H`)

## Server Configuration

### Alarm Config

Here's a example:

```
alarm_conditions = USED > 95%%, FREE < 5G
```

It will trigger alarm if `used / total > 0.95 or free < 5 * (1024**3)`

#### Alarm Conditions Syntax

Please notice that we use `%%` because of
[the feature](https://docs.python.org/3/library/configparser.html#configparser.BasicInterpolation)
from configparser package

``` ebnf
digit_wo_zero ::= "1" | "2" | "3" | "4" | "5" | "6" | "7" | "8" | "9";
digit         ::= "0" | digit_wo_zero;
integer       ::= digit | digit_wo_zero { digit };
percent_char  ::= "%%";
percentage    ::= digit percent_char | digit_wo_zero digit percent_char | "100" percent_char;
size_suffix   ::= "K" | "M" | "G" | "T" | "P";
size          ::= integer size_suffix | integer;
comparator    ::= ">" | ">=" | "==" | "<=" | "<";
variable      ::= "USED" | "FREE" | "RATE";
value         ::= percentage | size;
space         ::= " " | "\t";
spaces        ::= space | { space };
any_spaces    ::= "" | spaces;
condition     ::= variable any_spaces comparator any_spaces value;
conditions    ::= condition | condition { any_spaces "," any_spaces condition };
```

### Environment Variables

- `DISKU_CONFIG_FILE` - Path to config file to be loaded
- `DISKU_LOG_FILE` - Path to logfile, empty for standard output
- `DISKU_LOG_LEVEL` - One of (`DEBUG`, `INFO`, `WARN`, `ERROR`, `FATAL`), default is `ERROR`

## Agent Configuration

### Environment Variables

- `DISKU_LOG_FILE` - Path to logfile, empty for standard output
- `DISKU_LOG_LEVEL` - One of (`DEBUG`, `INFO`, `WARN`, `ERROR`, `FATAL`), default is `ERROR`

## Deployment

```sh
# 1. Clone this project
# 2. Install dependency
# 3. Install nginx, uwsgi, uwsgi-plugin-python3
# 4. Config uwsgi and nginx
```

## TODO

- [ ] Detailed deployment instructions
- [ ] Version number
- [ ] Support float point value in `size`
- [ ] More flexiability for webhook
- [ ] Make a DSL or python plugin architecture for advanced customized conditions
- [ ] More alarm channel provider
- [ ] Unit test
- [ ] Publish to PYPI

## License

This project is released under [MIT License](LICENSE)
