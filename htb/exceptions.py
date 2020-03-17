#!/usr/bin/env python3


class AlreadyEnumerated(Exception):
    """ The machine was already enumerated """

    pass


class NotApplicable(Exception):
    """ The given service was not applicable to the scanner """

    pass


class ConnectionNotFound(Exception):
    """ No NetworkManager connection found in the configuration file """

    pass


class TwoFactorAuthRequired(Exception):
    """ During authentication, the user was prompted for 2FA. """

    pass


class InvalidConnectionID(Exception):
    """ The specified NetworkManager connection UUID doesn't exist """

    pass


class AuthFailure(Exception):
    """ Authentication Failure """

    pass


class RequestFailed(Exception):
    """ A request recieved a negative response from the server """

    pass


class NotRunning(Exception):
    """ The requested machine is not running """

    pass


class Terminating(Exception):
    """ The requested machine is currently terminating """

    pass


class NoAnalysisPath(Exception):
    """ The requested machine does not have an active analysis directory """

    pass


class EtcHostsFailed(Exception):
    """ Adding the machine to /etc/hosts failed """

    pass


class MasscanFailed(Exception):
    """ Masscan attempt failed """

    pass


class NmapFailed(Exception):
    """ Nmap attempt failed """

    pass
