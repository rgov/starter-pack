"""Unpack downloaded files to the appropriate place.

Includes generic unzipping to a location, automatic handling of utilities
and other special categories, and individual logic for other files.

Many functions are VERY tightly coupled to the contents of config.yml
"""

import collections
import datetime
import glob
import json
import os
import shutil
import yaml
import zipfile

from . import component
from . import paths


def overwrite_dir(src, dest):
    """Copies a tree from src to dest, adding files."""
    if os.path.isdir(src):
        if not os.path.isdir(dest):
            os.makedirs(dest)
        for f in os.listdir(src):
            overwrite_dir(os.path.join(src, f), os.path.join(dest, f))
    else:
        shutil.copy(src, os.path.dirname(dest))


def unzip_to(filename, target_dir, *, makedirs=True):
    """Extract the contents of the given archive to the target directory.

    - If the filename is not a zip file, copy '.exe's to target_dir.
        For other file types, print a warning (everyone uses .zip for now)
    - If the zip is all in a single compressed folder, traverse it.
        We want the target_dir to hold files, not a single subdir.
    """
    print('{:20}  ->  {}'.format(os.path.basename(filename)[:20], target_dir))
    if makedirs:
        try:
            os.makedirs(target_dir)
        except FileExistsError:
            pass
    if not filename.endswith('.zip'):
        if filename.endswith('.exe'):
            # Rare utilities, basically just Dorven Realms
            shutil.copy(filename, target_dir)
            return
        raise ValueError('Only .zip and .exe files are handled by unzip_to()')
    if not zipfile.is_zipfile(filename):
        raise ValueError(filename + ' is not a valid .zip file.')

    with zipfile.ZipFile(filename) as zf:
        contents = [a for a in zip(zf.infolist(), zf.namelist())
                    if not a[1].endswith('/')]
        while len(set(n.partition('/')[0] for o, n in contents)) == 1:
            if len(contents) == 1:
                break
            contents = [(o, n.partition('/')[-1]) for o, n in contents]
        for obj, name in contents:
            outfile = os.path.join(target_dir, name)
            if not os.path.isdir(os.path.dirname(outfile)):
                os.makedirs(os.path.dirname(outfile))
            with open(outfile, 'wb') as out:
                shutil.copyfileobj(zf.open(obj), out)


def rough_simplify(df_dir):
    """Remove all files except data, raw, and manifests.json"""
    for fname in os.listdir(df_dir):
        path = os.path.join(df_dir, fname)
        if os.path.isfile(path):
            if fname != 'manifest.json':
                os.remove(path)
        elif fname not in {'data', 'raw'}:
            shutil.rmtree(path)


def install_lnp_dirs():
    """Install the LNP subdirs that I can't create automatically."""
    for d in ('colors', 'embarks', 'extras', 'tilesets'):
        shutil.copytree(paths.base(d), paths.lnp(d))
    overwrite_dir(paths.lnp('extras'), paths.df())
    for img in {'curses_640x300', 'curses_800x600',
                'curses_square_16x16', 'mouse'}:
        shutil.copy(paths.curr_baseline('data', 'art', img + '.png'),
                    paths.lnp('tilesets'))
    overwrite_dir(paths.lnp('tilesets'), paths.df('data', 'art'))


def make_defaults():
    """Create and install LNP/Defaults - embark profiles, Phoebus settings."""
    default_dir = paths.lnp('defaults')
    os.makedirs(default_dir)
    shutil.copy(paths.lnp('embarks', 'default_profiles.txt'), default_dir)
    for f in {'init.txt', 'd_init.txt'}:
        shutil.copy(paths.graphics('Phoebus', 'data', 'init', f), default_dir)
    overwrite_dir(default_dir, paths.df('data', 'init'))


def _keybinds_serialiser(lines):
    """Turn lines into an ordered dict, to preserve structure of file."""
    od, lastkey = collections.OrderedDict(), None
    for line in (l.strip() for l in lines):
        if line and line.startswith('[BIND:'):
            od[line], lastkey = [], line
        elif line:
            if lastkey is not None:
                od[lastkey].append(line)
    return od


def make_keybindings():
    """Create and install LNP/keybindings files from the vanilla files."""
    os.makedirs(paths.lnp('keybindings'))
    van_file = paths.df('data', 'init', 'interface.txt')
    shutil.copy(van_file, paths.lnp('keybindings', 'Vanilla DF.txt'))
    with open(van_file, encoding='cp437') as f:
        vanbinds = _keybinds_serialiser(f.readlines())
    for fname in os.listdir(paths.base('keybindings')):
        with open(paths.base('keybindings', fname)) as f:
            cfg = _keybinds_serialiser(f.readlines())
        lines = []
        for bind, vals in vanbinds.items():
            lines.append(bind)
            if bind in cfg:
                lines.extend(cfg[bind])
            else:
                lines.extend(vals)
        with open(paths.lnp('keybindings', fname), 'w', encoding='cp437') as f:
            f.write('\n' + '\n'.join(lines))


def _soundsense_xml():
    """Check and update version strings in xml path config"""
    xmlfile = paths.utilities('Soundsense', 'configuration.xml')
    relpath = os.path.relpath(paths.df(), paths.utilities('Soundsense'))
    with open(xmlfile) as f:
        config = f.readlines()
    for n, line in enumerate(config):
        if 'gamelog.txt' in line:
            config[n] = '\t<gamelog encoding="Cp850" path="{}"/>\n'.format(
                os.path.join(relpath, 'gamelog.txt'))
        elif 'ss_fix.log' in line:
            config[n] = '\t\t<item path="{}"/>\n'.format(
                os.path.join(relpath, 'ss_fix.log'))
    with open(xmlfile, 'w') as f:
        f.writelines(config)


def create_utilities():
    """Extract all utilities to the build/LNP/Utilities dir."""
    for comp in component.UTILITIES:
        unzip_to(comp.path, paths.lnp(comp.category, comp.name))
    _soundsense_xml()
    # Only keep 64bit World Viewer
    tmp = paths.utilities('DFWV')
    shutil.move(paths.utilities('World Viewer', '64bit'), tmp)
    shutil.copy(paths.utilities('World Viewer', 'Readme.txt'), tmp)
    shutil.rmtree(paths.utilities('World Viewer'))
    shutil.move(tmp, paths.utilities('World Viewer'))
    # Add xml for PerfectWorld, blueprints for Quickfort
    unzip_to(component.ALL['PerfectWorld XML'].path,
             paths.utilities('PerfectWorld'))
    unzip_to(component.ALL['Quickfort Blueprints'].path,
             paths.utilities('Quickfort', 'blueprints'))
    # generate utilities.txt (waiting for a decent utility config format)
    with open(paths.utilities('utilities.txt'), 'w') as f:
        for util in component.UTILITIES:
            if util.name == 'Quickfort':
                f.write('[Quickfort.exe:Quickfort:{}]\n'.format(util.tooltip))
                f.write('[qfconvert.exe:EXCLUDE]\n')
                continue
            exe, jars = [], []
            for _, _, files in os.walk(paths.utilities(util.name)):
                for fname in files:
                    if fname.endswith('.exe'):
                        exe.append(fname)
                    elif fname.endswith('.jar'):
                        jars.append(fname)
            for j in jars:
                f.write('[{}:EXCLUDE]\n'.format(j))
            if len(exe) == 1:
                f.write('[{}:{}:{}]\n'.format(exe[0], util.name, util.tooltip))
            else:
                print('WARNING:  found {} in {}'.format(exe, util.name))


def _twbt_settings(pack):
    """Set TwbT-specific options for a graphics pack."""
    init_file = paths.graphics(pack, 'data', 'init', 'init.txt')
    with open(init_file) as f:
        init = f.readlines()
    for n, _ in enumerate(init):
        if init[n].startswith('[FONT:') and pack != 'CLA':
            init[n] = '[FONT:curses_640x300.png]\n'
        elif init[n].startswith('[FULLFONT:') and pack != 'CLA':
            init[n] = '[FULLFONT:curses_640x300.png]\n'
        elif init[n].startswith('[PRINT_MODE:'):
            init[n] = '[PRINT_MODE:TWBT]\n'
    with open(init_file, 'w') as f:
        f.writelines(init)


def _make_ascii_graphics():
    """Create the ASCII graphics pack from a DF zip."""
    unzip_to(component.ALL['Dwarf Fortress'].path,
             paths.graphics('ASCII'))
    manifest = {"author": "ToadyOne","content_version": paths.DF_VERSION,
                "tooltip": "Default graphics for DF, exactly as they come."}
    with open(paths.graphics('ASCII', 'manifest.json'), 'w') as f:
        json.dump(manifest, f, indent=4)


def create_graphics():
    """Extract all graphics packs to the build/LNP/Graphics dir."""
    # Unzip all packs
    for comp in component.GRAPHICS:
        unzip_to(comp.path, paths.lnp(comp.category, comp.name))
    _make_ascii_graphics()
    # Only keep the 24px edition of Gemset
    gemset = glob.glob(paths.graphics('Gemset', '*_24px'))[0]
    shutil.move(gemset, paths.graphics('_temp'))
    shutil.rmtree(paths.graphics('Gemset'))
    shutil.move(paths.graphics('_temp'), paths.graphics('Gemset'))

    for pack in os.listdir(paths.graphics()):
        # Reduce filesize of graphics packs
        rough_simplify(paths.graphics(pack))
        tilesets = os.listdir(paths.lnp('tilesets'))
        for file in os.listdir(paths.graphics(pack, 'data', 'art')):
            if file in tilesets or file.endswith('.bmp'):
                os.remove(paths.graphics(pack, 'data', 'art', file))
        # Check that all is well...
        files = os.listdir(paths.graphics(pack))
        if not ('data' in files and 'raw' in files):
            print(pack + ' graphics pack malformed!')
        elif len(files) > 3:
            print(pack + ' graphics pack not simplified!')
        # Set up TwbT config...
        if pack not in {'ASCII', 'Gemset'}:
            _twbt_settings(pack)


def create_df_dir():
    """Create the Dwarf Fortress directory, with DFHack and other content."""
    # Extract the items below
    items = ['Dwarf Fortress', 'DFHack', 'Stocksettings']
    destinations = [paths.df(), paths.df(), paths.df('stocksettings')]
    for item, path in zip(items, destinations):
        comp = component.ALL[item]
        unzip_to(comp.path, path)
    # Rename the example init file
    os.rename(paths.df('dfhack.init-example'), paths.df('dfhack.init'))
    # install TwbT
    plugins = ['{}/{}.plug.dll'.format(
        component.ALL['DFHack'].version.replace('v', ''), plug)
               for plug in ('automaterial', 'mousequery', 'resume', 'twbt')]
    done = False
    with zipfile.ZipFile(component.ALL['TwbT'].path) as zf:
        for obj, name in zip(zf.infolist(), zf.namelist()):
            if name in plugins:
                done = True
                outpath = paths.df('hack', 'plugins', os.path.basename(name))
                with open(outpath, 'wb') as out:
                    shutil.copyfileobj(zf.open(obj), out)
    if not done:
        print('WARNING:  TwbT not installed; not compatible with DFHack.')


def create_baselines():
    """Extract the data and raw dirs of vanilla DF to LNP/Baselines."""
    unzip_to(component.ALL['Dwarf Fortress'].path, paths.curr_baseline())
    rough_simplify(paths.curr_baseline())


def _contents():
    """Make LNP/about/contents.txt from a template."""
    def link(comp, ver=True, dash=' - '):
        """Return BBCode format link to the component."""
        vstr = ' ' + comp.version if ver else ''
        return dash + '[url={}]{}[/url]'.format(comp.page, comp.name + vstr)

    kwargs = {c.name: link(c, dash='') for c in component.FILES}
    kwargs['graphics'] = '\n'.join(link(c, False) for c in component.GRAPHICS)
    kwargs['utilities'] = '\n'.join(link(c) for c in component.UTILITIES)
    with open(paths.base('changelog.txt')) as f:
        kwargs['changelogs'] = '\n\n'.join(f.read().split('\n\n')[:5])
    with open(paths.base('contents.txt')) as f:
        template = f.read()
    for item in kwargs:
        if '{' + item + '}' not in template:
            raise ValueError(item + ' not listed in base/docs/contents.txt')
    with open(paths.lnp('about', 'contents.txt'), 'w') as f:
        #pylint:disable=star-args
        f.write(template.format(**kwargs))


def create_about():
    """Create the LNP/About folder contents."""
    # about.txt
    if not os.path.isdir(paths.lnp('about')):
        os.mkdir(paths.lnp('about'))
    shutil.copy(paths.base('about.txt'), paths.lnp('about'))
    # changelog.txt
    with open(paths.base('changelog.txt')) as f:
        changelog = f.readlines()
    # TODO:  conditional insertion, write updated header back to base file
    # TODO:  Include checksum with each changelog entry
        changelog.insert(0, 'Version {} ({})\n'.format(
            paths.PACK_VERSION, datetime.date.today().isoformat()))
        with open(paths.lnp('about', 'changelog.txt'), 'w') as f:
            f.writelines(changelog)
    _contents()


def setup_pylnp():
    """Extract PyLNP and copy PyLNP.json from ./base"""
    unzip_to(component.ALL['PyLNP'].path, paths.build())
    os.rename(paths.build('PyLNP.exe'),
              paths.build('Starter Pack Launcher (PyLNP).exe'))
    os.remove(paths.build('PyLNP.json'))
    with open(paths.base('PyLNP-json.yml')) as f:
        pylnp_conf = yaml.load(f)
    pylnp_conf['updates']['packVersion'] = paths.PACK_VERSION
    with open(paths.lnp('PyLNP.json'), 'w') as f:
        json.dump(pylnp_conf, f, indent=2)
    if component.ALL['PyLNP'].version == '0.10b':
        with open(paths.df('PyLNP_dfhack_onLoad.init'), 'w') as f:
            f.write('# Placeholder file.\n')
    else:
        print('Can remove old PyLNP DFHack init code now.')


def build_all():
    """Build all components, in the required order."""
    print('\nBuilding pack...')
    if os.path.isdir('build'):
        shutil.rmtree('build')
    create_df_dir()
    create_baselines()
    install_lnp_dirs()
    create_utilities()
    create_graphics()
    overwrite_dir(paths.graphics('Phoebus'), paths.df())
    setup_pylnp()
    create_about()
    make_defaults()
    make_keybindings()
