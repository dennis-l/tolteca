#! /usr/bin/env python


def pformat_paths(paths, sep='\n'):
    return sep.join(f'{p!s}' for p in paths)


def pformat_list(l, indent, minw=60, fancy=True):
    if not l or not l[0]:
        width = None
    else:
        width = [max(len(str(e[i])) for e in l) for i in range(len(l[0]))]

    def fmt_elem(e, width=width, fancy=fancy):
        if len(e) == 1:
            return "{}".format(e)
        else:
            if width is not None and (fancy or len(e) == 2):
                if fancy:
                    fmt = '| {} |'.format(
                           ' | '.join("{{:<{}s}}".format(w) for w in width))
                else:  # len(e) == 2
                    fmt = "{{:<{}s}}: {{}}".format(width[0])
            elif len(e) == 2:
                fmt = "{}: {}"
            else:
                fmt = ", ".join("{}" for _ in e)
            if (len(e) == 2) and isinstance(e[1], (float)):
                return fmt.format(str(e[0]), "{:g}".format(e[1]))
            if len(e) == 2 and hasattr(e[1], 'items'):
                return fmt.format(
                        str(e[0]), pformat_dict(e[1], indent=indent + 2))
            return fmt.format(*map(str, e))
    flat = "[{}]".format(
            ', '.join(map(lambda e: fmt_elem(e, width=None), l)))
    if len(flat) > minw:
        fmt = "{{:{}s}}{{}}".format(indent)
        return "\n{}".format(
                '\n'.join(fmt.format(" ", fmt_elem(e)) for e in l))
    else:
        return flat


def pformat_dict(d, indent=2, minw=60):
    return pformat_list([e for e in d.items()], indent, fancy=False)
