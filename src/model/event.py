# http://pyrocko.org - GPLv3
#
# The Pyrocko Developers, 21st Century
# ---|P------/S----------~Lg----------
from __future__ import absolute_import, division

from past.builtins import cmp
import logging
import numpy as num
import hashlib
import base64

from pyrocko import util, moment_tensor

from pyrocko.guts import Float, String, Timestamp, Unicode, \
    StringPattern, List
from .location import Location

logger = logging.getLogger('pyrocko.model.event')

guts_prefix = 'pf'

d2r = num.pi / 180.


def ehash(s):
    return str(base64.urlsafe_b64encode(
        hashlib.sha1(s.encode('utf8')).digest()).decode('ascii'))


def float_or_none_to_str(x, prec=9):
    return 'None' if x is None else '{:.{prec}e}'.format(x, prec=prec)


class FileParseError(Exception):
    pass


class EOF(Exception):
    pass


class EmptyEvent(Exception):
    pass


class Tag(StringPattern):
    pattern = r'^[A-Za-z][A-Za-z0-9._]{0,128}:[A-Za-z0-9._-]+$'


class Event(Location):
    '''Seismic event representation

    :param lat: latitude of hypocenter (default 0.0)
    :param lon: longitude of hypocenter (default 0.0)
    :param time: origin time as float in seconds after '1970-01-01 00:00:00
    :param name: event identifier as string (optional)
    :param depth: source depth (optional)
    :param magnitude: magnitude of event (optional)
    :param region: source region (optional)
    :param catalog: name of catalog that lists this event (optional)
    :param moment_tensor: moment tensor as
        :py:class:`moment_tensor.MomentTensor` instance (optional)
    :param duration: source duration as float (optional)
    '''

    time = Timestamp.T(default=util.str_to_time('1970-01-01 00:00:00'))
    name = String.T(default='', optional=True)
    magnitude = Float.T(optional=True)
    magnitude_type = String.T(optional=True)
    region = Unicode.T(optional=True)
    catalog = String.T(optional=True)
    moment_tensor = moment_tensor.MomentTensor.T(optional=True)
    duration = Float.T(optional=True)
    tags = List.T(Tag.T(optional=True))

    def __init__(
            self, lat=0., lon=0., time=0., name='', depth=None, elevation=None,
            magnitude=None, magnitude_type=None, region=None, load=None,
            loadf=None, catalog=None, moment_tensor=None, duration=None,
            tags=[]):

        vals = None
        if load is not None:
            vals = Event.oldload(load)
        elif loadf is not None:
            vals = Event.oldloadf(loadf)

        if vals:
            lat, lon, time, name, depth, magnitude, magnitude_type, region, \
                catalog, moment_tensor, duration, tags = vals

        Location.__init__(
            self, lat=lat, lon=lon, time=time, name=name, depth=depth,
            elevation=elevation,
            magnitude=magnitude, magnitude_type=magnitude_type,
            region=region, catalog=catalog,
            moment_tensor=moment_tensor, duration=duration, tags=tags)

    def time_as_string(self):
        return util.time_to_str(self.time)

    def set_name(self, name):
        self.name = name

    def olddump(self, filename):
        file = open(filename, 'w')
        self.olddumpf(file)
        file.close()

    def olddumpf(self, file):
        file.write('name = %s\n' % self.name)
        file.write('time = %s\n' % util.time_to_str(self.time))
        if self.lat is not None:
            file.write('latitude = %.12g\n' % self.lat)
        if self.lon is not None:
            file.write('longitude = %.12g\n' % self.lon)
        if self.magnitude is not None:
            file.write('magnitude = %g\n' % self.magnitude)
            file.write('moment = %g\n' %
                       moment_tensor.magnitude_to_moment(self.magnitude))
        if self.magnitude_type is not None:
            file.write('magnitude_type = %s\n' % self.magnitude_type)
        if self.depth is not None:
            file.write('depth = %.10g\n' % self.depth)
        if self.region is not None:
            file.write('region = %s\n' % self.region)
        if self.catalog is not None:
            file.write('catalog = %s\n' % self.catalog)
        if self.moment_tensor is not None:
            m = self.moment_tensor.m()
            sdr1, sdr2 = self.moment_tensor.both_strike_dip_rake()
            file.write((
                'mnn = %g\nmee = %g\nmdd = %g\nmne = %g\nmnd = %g\nmed = %g\n'
                'strike1 = %g\ndip1 = %g\nrake1 = %g\n'
                'strike2 = %g\ndip2 = %g\nrake2 = %g\n') % (
                    (m[0, 0], m[1, 1], m[2, 2], m[0, 1], m[0, 2], m[1, 2]) +
                    sdr1 + sdr2))

        if self.duration is not None:
            file.write('duration = %g\n' % self.duration)

        if self.tags:
            file.write('tags = %s\n' % ', '.join(self.tags))

    @staticmethod
    def unique(events, deltat=10., group_cmp=(lambda a, b:
                                              cmp(a.catalog, b.catalog))):
        groups = Event.grouped(events, deltat)

        events = []
        for group in groups:
            if group:
                group.sort(group_cmp)
                events.append(group[-1])

        return events

    @staticmethod
    def grouped(events, deltat=10.):
        events = list(events)
        groups = []
        for ia, a in enumerate(events):
            groups.append([])
            haveit = False
            for ib, b in enumerate(events[:ia]):
                if abs(b.time - a.time) < deltat:
                    groups[ib].append(a)
                    haveit = True
                    break

            if not haveit:
                groups[ia].append(a)

        groups = [g for g in groups if g]
        groups.sort(key=lambda g: sum(e.time for e in g) // len(g))
        return groups

    @staticmethod
    def dump_catalog(events, filename=None, stream=None):
        if filename is not None:
            file = open(filename, 'w')
        else:
            file = stream
        try:
            i = 0
            for ev in events:

                ev.olddumpf(file)

                file.write('--------------------------------------------\n')
                i += 1

        finally:
            if filename is not None:
                file.close()

    @staticmethod
    def oldload(filename):
        with open(filename, 'r') as file:
            return Event.oldloadf(file)

    @staticmethod
    def oldloadf(file):
        d = {}
        try:
            for line in file:
                if line.lstrip().startswith('#'):
                    continue

                toks = line.split(' = ', 1)
                if len(toks) == 2:
                    k, v = toks[0].strip(), toks[1].strip()
                    if k in ('name', 'region', 'catalog', 'magnitude_type'):
                        d[k] = v
                    if k in (('latitude longitude magnitude depth duration '
                              'mnn mee mdd mne mnd med strike1 dip1 rake1 '
                              'strike2 dip2 rake2 duration').split()):
                        d[k] = float(v)
                    if k == 'time':
                        d[k] = util.str_to_time(v)
                    if k == 'tags':
                        d[k] = [x.strip() for x in v.split(',')]

                if line.startswith('---'):
                    d['have_separator'] = True
                    break

        except Exception as e:
            raise FileParseError(e)

        if not d:
            raise EOF()

        if 'have_separator' in d and len(d) == 1:
            raise EmptyEvent()

        mt = None
        m6 = [d[x] for x in 'mnn mee mdd mne mnd med'.split() if x in d]
        if len(m6) == 6:
            mt = moment_tensor.MomentTensor(m=moment_tensor.symmat6(*m6))
        else:
            sdr = [d[x] for x in 'strike1 dip1 rake1'.split() if x in d]
            if len(sdr) == 3:
                moment = 1.0
                if 'moment' in d:
                    moment = d['moment']
                elif 'magnitude' in d:
                    moment = moment_tensor.magnitude_to_moment(d['magnitude'])

                mt = moment_tensor.MomentTensor(
                    strike=sdr[0], dip=sdr[1], rake=sdr[2],
                    scalar_moment=moment)

        return (
            d.get('latitude', 0.0),
            d.get('longitude', 0.0),
            d.get('time', 0.0),
            d.get('name', ''),
            d.get('depth', None),
            d.get('magnitude', None),
            d.get('magnitude_type', None),
            d.get('region', None),
            d.get('catalog', None),
            mt,
            d.get('duration', None),
            d.get('tags', []))

    @staticmethod
    def load_catalog(filename):

        file = open(filename, 'r')

        try:
            while True:
                try:
                    ev = Event(loadf=file)
                    yield ev
                except EmptyEvent:
                    pass

        except EOF:
            pass

        file.close()

    def get_hash(self):
        e = self
        if isinstance(e.time, util.hpfloat):
            stime = util.time_to_str(e.time, format='%Y-%m-%d %H:%M:%S.6FRAC')
        else:
            stime = util.time_to_str(e.time, format='%Y-%m-%d %H:%M:%S.3FRAC')

        s = float_or_none_to_str

        to_hash = ', '.join((
            stime,
            s(e.lat), s(e.lon), s(e.depth),
            float_or_none_to_str(e.magnitude, 5),
            str(e.catalog), str(e.name or ''),
            str(e.region)))

        return ehash(to_hash)

    def human_str(self):
        s = [
            'Latitude [deg]: %g' % self.lat,
            'Longitude [deg]: %g' % self.lon,
            'Time [UTC]: %s' % util.time_to_str(self.time)]

        if self.name:
            s.append('Name: %s' % self.name)

        if self.depth is not None:
            s.append('Depth [km]: %g' % (self.depth / 1000.))

        if self.magnitude is not None:
            s.append('Magnitude [%s]: %3.1f' % (
                self.magnitude_type or 'M?', self.magnitude))

        if self.region:
            s.append('Region: %s' % self.region)

        if self.catalog:
            s.append('Catalog: %s' % self.catalog)

        if self.moment_tensor:
            s.append(str(self.moment_tensor))

        return '\n'.join(s)


def detect_format(filename):
    with open(filename, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or line.startswith('%'):
                continue
            if line.startswith('--- !pf.Event'):
                return 'yaml'
            else:
                return 'basic'


def load_events(filename, format='detect'):
    '''Read events file.

    :param filename: name of file as str
    :param format: file format: ``'detect'``, ``'basic'``, or ``'yaml'``
    :returns: list of :py:class:`Event` objects
    '''

    if format == 'detect':
        fmt = detect_format(filename)

    assert fmt in ('yaml', 'basic')

    if fmt == 'yaml':
        from pyrocko import guts
        events = [
            ev for ev in guts.load_all(filename=filename)
            if isinstance(ev, Event)]

        return events
    elif fmt == 'basic':
        return list(Event.load_catalog(filename))
    else:
        from pyrocko.io.io_common import FileLoadError
        FileLoadError('unknown event file format: %s' % fmt)


class OneEventRequired(Exception):
    pass


def load_one_event(filename, format='detect'):
    events = load_events(filename)
    if len(events) != 1:
        raise OneEventRequired(
            'exactly one event is required in "%s"' % filename)

    return events[0]


def dump_events(events, filename=None, stream=None):
    '''Write events file.

    :param events: list of :py:class:`Event` objects
    :param filename: name of file as str
    '''
    Event.dump_catalog(events, filename=filename, stream=stream)


def load_kps_event_list(filename):
    elist = []
    f = open(filename, 'r')
    for line in f:
        toks = line.split()
        if len(toks) < 7:
            continue

        tim = util.ctimegm(toks[0]+' '+toks[1])
        lat, lon, depth, magnitude = [float(x) for x in toks[2:6]]
        duration = float(toks[10])
        region = toks[-1]
        name = util.gmctime_fn(tim)
        e = Event(
            lat, lon, tim,
            name=name,
            depth=depth,
            magnitude=magnitude,
            duration=duration,
            region=region)

        elist.append(e)

    f.close()
    return elist


def load_gfz_event_list(filename):
    from pyrocko import catalog
    cat = catalog.Geofon()

    elist = []
    f = open(filename, 'r')
    for line in f:
        e = cat.get_event(line.strip())
        elist.append(e)

    f.close()
    return elist
