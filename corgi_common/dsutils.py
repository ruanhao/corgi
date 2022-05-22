def flatten0(L):
    if not isinstance(L, (list, tuple, set)):
        yield L
        return
    for F in L:
        yield from flatten(F)


def flatten(L):
    return list(flatten0(L))
