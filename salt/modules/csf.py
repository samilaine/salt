# -*- coding: utf-8 -*-
'''
Support for Config Server Firewall (CSF)
========================================
:maintainer: Mostafa Hussein <mostafa.hussein91@gmail.com>
:maturity: new
:platform: Linux
'''

# Import Python Libs
from __future__ import absolute_import

# Import Salt Libs
from salt.exceptions import CommandExecutionError, SaltInvocationError
import salt.utils


def __virtual__():
    '''
    Only load if csf exists on the system
    '''
    if salt.utils.which('csf') is None:
        return (False,
                'The csf execution module cannot be loaded: csf unavailable.')
    else:
        return True


def _temp_exists(method, ip):
    '''
    Checks if the ip exists as a temporary rule based
    on the method supplied, (tempallow, tempdeny).
    '''
    _type = method.replace('temp', '').upper()
    cmd = "csf -t | awk -v code=1 -v type=_type -v ip=ip '$1==type && $2==ip {{code=0}} END {{exit code}}'".format(_type, ip)
    exists = __salt__['cmd.run_all'](cmd)
    return not bool(exists['retcode'])


def _exists_with_port(method, rule):
    path = '/etc/csf/csf.{0}'.format(method)
    return __salt__['file.contains'](path, rule)
    

def exists(method,
            ip,
            port=None,
            proto='tcp',
            direction='in',
            port_origin='d',
            ip_origin='d',
            ttl=None,
            comment=''):
    '''
    Returns true a rule for the ip already exists 
    based on the method supplied. Returns false if 
    not found.
    CLI Example:
    .. code-block:: bash
        salt '*' csf.exists allow 1.2.3.4
        salt '*' csf.exists tempdeny 1.2.3.4
    '''
    if method.startswith('temp'):
        return _temp_exists(method, ip)
    if port:
        rule = _build_port_rule(ip, port, proto, direction, port_origin, ip_origin, comment)
        return _exists_with_port(method, rule)
    exists = __salt__['cmd.run_all']("egrep ^'{0} +' /etc/csf/csf.{1}".format(ip, method))
    return not bool(exists['retcode'])


def __csf_cmd(cmd):
    '''
    Execute csf command
    '''
    csf_cmd = '{0} {1}'.format(salt.utils.which('csf'), cmd)
    out = __salt__['cmd.run_all'](csf_cmd)

    if out['retcode'] != 0:
        if not out['stderr']:
            ret = out['stdout']
        else:
            ret = out['stderr']
        raise CommandExecutionError(
            'csf failed: {0}'.format(msg)
        )
    else:
        ret = out['stdout']
    return ret


def _status_csf():
    '''
    Return True if csf is running otherwise return False
    '''
    cmd = 'test -e /etc/csf/csf.disable'
    out = __salt__['cmd.run_all'](cmd)
    return bool(out['retcode'])


def _get_opt(method):
    '''
    Returns the cmd option based on a long form argument.
    '''
    opts = {
        'allow': '-a',
        'deny': '-d',
        'unallow': '-ar',
        'undeny': '-dr',
        'tempallow': '-ta',
        'tempdeny': '-td',
        'temprm': '-tr'
    }
    return opts[method]


def _build_args(method, ip, comment):
    '''
    Returns the cmd args for csf basic allow/deny commands.
    '''
    opt = _get_opt(method)
    args = '{0} {1}'.format(opt, ip)
    if comment:
        args += ' {0}'.format(comment)
    return args


def _access_rule(method,
                ip=None,
                port=None,
                proto='tcp',
                direction='in',
                port_origin='d',
                ip_origin='d',
                comment=''):
    '''
    Handles the cmd execution for allow and deny commands.
    '''
    if _status_csf():
        if ip is None:
            return {'error': 'You must supply an ip address or CIDR.'}
        if port is None:
            args = _build_args(method, ip, comment)
            return __csf_cmd(args)
        else:
            if method not in ['allow', 'deny']:
                return {'error': 'Only allow and deny rules are allowed when specifying a port.'}
            return _access_rule_with_port(method, ip, port, proto, direction, port_origin, ip_origin, comment)

def _build_port_rule(ip, port, proto, direction, port_origin, ip_origin, comment):
    kwargs = {
        'ip': ip,
        'port': port,
        'proto': proto,
        'direction': direction,
        'port_origin': port_origin,
        'ip_origin': ip_origin,
    }
    rule = '{proto}|{direction}|{port_origin}={port}|{ip_origin}={ip}'.format(**kwargs)
    if comment:
        rule += ' #{0}'.format(comment)
    
    return rule

def _remove_access_rule_with_port(method,
                                    ip,
                                    port,
                                    proto,
                                    port_origin,
                                    ip_origin):
    rule = _build_port_rule(ip,
                            port,
                            proto,
                            direction,
                            port_origin,
                            ip_origin)

    result = __salt__['file.replace']('/etc/csf/csf.{0}'.format(method),
                                        '^{0} +\#.*$\n'.format(rule),
                                        '')

    return result


def _csf_to_list(option):
    '''
    Extract comma-separated values from a csf.conf
    option and return a list.
    '''
    result = []
    pattern = '^{0}(\ +)?\=(\ +)?".*"$'.format(option)
    grep = __salt__['file.grep']('/etc/csf/csf.conf', pattern, '-E')
    if not grep or grep['stderr']:
        raise CommandExecutionError(
            'Could not find {0} in csf.conf. grep stderr: {1}'.format(option, grep['stderr'])
        )
    if 'stdout' in grep and grep['stdout']:
        line = grep['stdout']
        csv = line.split('=')[1].replace(' ', '').replace('"', '')
        result = csv.split(',')
    return result


def get_skipped_nics(ipv6=False):
    if ipv6:
        option = 'ETH6_DEVICE_SKIP'
    else:
        option = 'ETH_DEVICE_SKIP'

    skipped_nics = _csf_to_list(option)
    return skipped_nics

def skip_nic(nic, ipv6=False):
    nics = get_skipped_nics(ipv6=ipv6)
    nics.append(nic)
    return skip_nics(nics, ipv6)

def skip_nics(nics, ipv6=False):
    if ipv6:
        ipv6 = '6'
    else:
        ipv6 = ''
    nics_csv = ','.join(map(str, nics))
    result = __salt__['file.replace']('/etc/csf/csf.conf',
                                        pattern='^ETH{0}_DEVICE_SKIP(\ +)?\=(\ +)?".*"'.format(ipv6),
                                        repl='ETH{0}_DEVICE_SKIP = "{1}"'.format(ipv6, nics_csv))

    return result


def _access_rule_with_port(method,
                            ip,
                            port,
                            proto='tcp', 
                            direction='in',
                            port_origin='d',
                            ip_origin='d',
                            ttl=None,
                            comment=''):

    results = {}
    if direction == 'both':
        for direction in ['in', 'out']:
            _exists = exists(method,
                                ip,
                                port=port,
                                proto=proto,
                                direction=direction,
                                port_origin=port_origin,
                                ip_origin=ip_origin,
                                ttl=ttl,
                                comment=comment)
            if not _exists:
                rule = _build_port_rule(ip,
                                        port=port,
                                        proto=proto,
                                        direction=direction,
                                        port_origin=port_origin,
                                        ip_origin=ip_origin,
                                        comment=comment)
                path = '/etc/csf/csf.{0}'.format(method)
                results[direction] = __salt__['file.append'](path, rule)
    return results


def _tmp_access_rule(method,
                    ip=None, 
                    ttl=None, 
                    port=None, 
                    direction='in',
                    port_origin='d',
                    ip_origin='d',
                    comment=''):
    '''
    Handles the cmd execution for tempdeny and tempallow commands.
    '''
    if _status_csf():
        if ip is None:
            return {'error': 'You must supply an ip address or CIDR.'}
        if ttl is None:
            return {'error': 'You must supply a ttl.'}
        args = _build_tmp_access_args(method, ip, ttl, port, direction, comment)
        return __csf_cmd(args)


def _build_tmp_access_args(method, ip, ttl, port, direction, comment):
    '''
    Builds the cmd args for temporary access/deny opts.
    '''
    opt = _get_opt(method)
    args = '{0} {1} {2}'.format(opt, ip, ttl)
    if port:
        args += ' -p {0}'.format(port)
    if direction:
        args += ' -d {0}'.format(direction)
    if comment:
        args += ' #{0}'.format(comment) 
    return args


def running():
    '''
    Check csf status
    CLI Example:
    .. code-block:: bash
        salt '*' csf.running
    '''
    return _status_csf()


def disable():
    '''
    Disable csf permanently
    CLI Example:
    .. code-block:: bash
        salt '*' csf.disable
    '''
    if _status_csf():
        return __csf_cmd('-x')


def enable():
    '''
    Activate csf if not running
    CLI Example:
    .. code-block:: bash
        salt '*' csf.enable
    '''
    if not _status_csf():
        return __csf_cmd('-e')


def reload():
    '''
    Restart csf
    CLI Example:
    .. code-block:: bash
        salt '*' csf.reload
    '''
    if not _status_csf():
        return __csf_cmd('-r')


def tempallow(ip=None, ttl=None, port=None, direction=None, comment=''):
    '''
    Add an rule to the temporary ip allow list.
    See :func:`_access_rule`.
    1- Add an IP:
    CLI Example:
    .. code-block:: bash
        salt '*' csf.tempallow 127.0.0.1 3600 port=22 direction='in' comment='# Temp dev ssh access'
    '''
    return _tmp_access_rule('tempallow', ip, ttl, port, direction, comment)

def tempdeny(ip=None, ttl=None, port=None, direction=None, comment=''):
    '''
    Add a rule to the temporary ip deny list.
    See :func:`_access_rule`.
    1- Add an IP:
    CLI Example:
    .. code-block:: bash
        salt '*' csf.tempdeny 127.0.0.1 300 port=22 direction='in' comment='# Brute force attempt'
    '''
    return _tmp_access_rule('tempdeny', ip, ttl, port, direction, comment)

def allow(ip,
        port=None,
        proto='tcp',
        direction='in',
        port_origin='d',
        ip_origin='s',
        ttl=None,
        comment=''):
    '''
    Add an rule to csf allowed hosts
    See :func:`_access_rule`.
    1- Add an IP:
    CLI Example:
    .. code-block:: bash
        salt '*' csf.allow 127.0.0.1
        salt '*' csf.allow 127.0.0.1 comment="Allow localhost"
    '''
    return _access_rule('allow',
                        ip,
                        port=port,
                        proto=proto,
                        direction=direction,
                        port_origin=port_origin,
                        ip_origin=ip_origin,
                        comment=comment)


def deny(ip,
        port=None,
        proto='tcp',
        direction='in',
        port_origin='d',
        ip_origin='d',
        ttl=None,
        comment=''):
    '''
    Add an rule to csf denied hosts
    See :func:`_access_rule`.
    1- Deny an IP:
    CLI Example:
    .. code-block:: bash
        salt '*' csf.deny 127.0.0.1
        salt '*' csf.deny 127.0.0.1 comment="Too localhosty"
    '''
    return _access_rule('deny', ip, port, proto, direction, port_origin, ip_origin, comment)


def remove_temp_rule(ip):
    opt = _get_opt('temprm')
    args = '{0} {1}'.format(ip)
    return __csf_cmd(args)


def unallow(ip):
    '''
    Remove a rule from the csf denied hosts
    See :func:`_access_rule`.
    1- Deny an IP:
    CLI Example:
    .. code-block:: bash
        salt '*' csf.unallow 127.0.0.1
    '''
    return _access_rule('unallow', ip)


def undeny(ip):
    '''
    Remove a rule from the csf denied hosts
    See :func:`_access_rule`.
    1- Deny an IP:
    CLI Example:
    .. code-block:: bash
        salt '*' csf.undeny 127.0.0.1
    '''
    return _access_rule('undeny', ip)

def remove_rule(method,
                ip,
                port=None,
                proto='tcp',
                direction='in',
                port_origin='d',
                ip_origin='s',
                ttl=None,
                comment=''):

    if method.startswith('temp') or ttl:
        return remove_temp_rule(ip)

    if not port:
        if method == 'allow':
            return unallow(ip)
        elif method == 'deny':
            return undeny(ip)

    if port:
        return _remove_access_rule_with_port(method,
                                            ip,
                                            port,
                                            proto,
                                            port_origin,
                                            ip_origin)


def allow_ports(ports, proto='tcp', direction='in'):
    '''
    Fully replace the incoming or outgoing ports
    line in the csf.conf file - e.g. TCP_IN, TCP_OUT,
    UDP_IN, UDP_OUT, etc.

    CLI Example:
    .. code-block:: bash
        salt '*' csf.allow_ports ports="[22,80,443,4505,4506]" proto='tcp' direction='in'
    '''

    results = []
    proto = proto.upper() 
    direction = direction.upper()
    _validate_direction_and_proto(direction, proto)
    ports_csv = ','.join(map(str, ports))
    directions = build_directions(direction)

    for direction in directions:
        result = __salt__['file.replace']('/etc/csf/csf.conf',
                                    pattern='^{0}_{1}(\ +)?\=(\ +)?".*"$'.format(proto, direction),
                                    repl='{0}_{1} = "{2}"'.format(proto, direction, ports_csv))
        results.append(result)

    return results

def get_ports(proto='tcp', direction='in'):
    '''
    Lists ports from csf.conf based on direction and protocol.
    e.g. - TCP_IN, TCP_OUT, UDP_IN, UDP_OUT, etc..

    CLI Example:
    .. code-block:: bash
        salt '*' csf.allow_port 22 proto='tcp' direction='in'
    '''

    proto = proto.upper()
    direction = direction.upper()
    results = {}
    _validate_direction_and_proto(direction, proto)
    directions = build_directions(direction)
    for direction in directions:
        option = '{0}_{1}'.format(proto, direction)
        results[direction] = _csf_to_list(option)

    return results


def _validate_direction_and_proto(direction, proto):
    if direction.upper() not in ['IN', 'OUT', 'BOTH']:
        raise SaltInvocationError(
            'You must supply a direction of in, out, or both'
        )
    if proto.upper() not in ['TCP', 'UDP', 'TCP6', 'UDP6']:
        raise SaltInvocationError(
            'You must supply tcp, udp, tcp6, or udp6 for the proto keyword'
        )
    return


def build_directions(direction):
    direction = direction.upper()
    if direction == 'BOTH':
        directions = ['IN', 'OUT']
    else:
        directions = [direction]
    return directions 


def allow_port(port, proto='tcp', direction='both'):
    '''
    Like allow_ports, but it will append to the 
    existing entry instead of replacing it.
    Takes a single port instead of a list of ports.

    CLI Example:
    .. code-block:: bash
        salt '*' csf.allow_port 22 proto='tcp' direction='in'
    '''

    ports = get_ports(proto=proto, direction=direction)
    direction = direction.upper()
    _validate_direction_and_proto(direction, proto)
    directions = build_directions(direction)
    results = []
    for direction in directions:
        _ports = ports[direction]
        _ports.append(port)
        results += allow_ports(_ports, proto=proto, direction=direction)
    return results

