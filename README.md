augprint.py
===========

`augprint.py` is a command-line utility which generates output suitable as input to the `augtool` from the augeas project.

The goal of `augprint.py` is to generate a series of `set` statements for `augtool` which will, for a given file,

* re-create the settings in that file
* do so in an idempotent manner ie. if re-applied to the same file, no changes are made

ie the following command should do nothing:

```
./augprint.py /etc/hosts | augtool 
```

The output of `augprint.py` differs from that of `augtool print` in that (almost) all sequential indexes are replaced with path expressions instead.

eg:

augtool print /files/etc/hosts

```
/files/etc/hosts
/files/etc/hosts/1
/files/etc/hosts/1/ipaddr = "127.0.0.1"
/files/etc/hosts/1/canonical = "localhost"
/files/etc/hosts/1/alias[1] = "localhost.localdomain"
/files/etc/hosts/1/alias[2] = "localhost4"
/files/etc/hosts/1/alias[3] = "localhost4.localdomain4"
/files/etc/hosts/2
/files/etc/hosts/2/ipaddr = "::1"
/files/etc/hosts/2/canonical = "localhost"
/files/etc/hosts/2/alias[1] = "localhost.localdomain"
/files/etc/hosts/2/alias[2] = "localhost6"
/files/etc/hosts/2/alias[3] = "localhost6.localdomain6"
```

augprint.py /etc/hosts

```
load-file /etc/hosts
set /files/etc/hosts/*[ipaddr='127.0.0.1'         ]/ipaddr  '127.0.0.1'
set /files/etc/hosts/*[ipaddr='127.0.0.1'         ]/canonical  'localhost'
set /files/etc/hosts/*[ipaddr='127.0.0.1'         ]/alias[.='localhost.localdomain']  'localhost.localdomain'
set /files/etc/hosts/*[ipaddr='127.0.0.1'         ]/alias[.='localhost4'        ]  'localhost4'
set /files/etc/hosts/*[ipaddr='127.0.0.1'         ]/alias[.='localhost4.localdomain4']  'localhost4.localdomain4'
set /files/etc/hosts/*[ipaddr='::1'               ]/ipaddr  '::1'
set /files/etc/hosts/*[ipaddr='::1'               ]/canonical  'localhost'
set /files/etc/hosts/*[ipaddr='::1'               ]/alias[.='localhost.localdomain']  'localhost.localdomain'
set /files/etc/hosts/*[ipaddr='::1'               ]/alias[.='localhost6'        ]  'localhost6'
set /files/etc/hosts/*[ipaddr='::1'               ]/alias[.='localhost6.localdomain6']  'localhost6.localdomain6'
```

The goal is to produce a set of _idempotent_ set commands that will add or modify existing entries.

This goal is not always achieved with augeas 1.12.0

Regardless of this shortcoming, the output of augprint.py provides a good starting point for creating idempotent augtool scripts, as it creates filter-path expressions that can often be used as-is.


Prerequistes
============

* python 3.x
* augeas
* python-augeas


Usage
=====

```
		augprint.py _filename_
```

Example
-------

```
		augprint.py /etc/hosts
```
