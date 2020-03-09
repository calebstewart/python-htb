#!/usr/bin/env python3


class AuthFailure(Exception):
    """ Authentication Failure """

    pass


class RequestFailed(Exception):
    """ A request recieved a negative response from the server """

    pass
