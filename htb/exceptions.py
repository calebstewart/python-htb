#!/usr/bin/env python3


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
