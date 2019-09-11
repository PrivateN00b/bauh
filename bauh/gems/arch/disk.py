import json
import os
import re
from pathlib import Path
from typing import Set, List

from bauh.gems.arch import pacman
from bauh.gems.arch.model import ArchPackage

RE_DESKTOP_ENTRY = re.compile(r'(Exec|Icon)\s*=\s*(.+)')
RE_CLEAN_NAME = re.compile(r'^(\w+)-?|_?.+')


def write(app: ArchPackage):
    Path(app.get_disk_cache_path()).mkdir(parents=True, exist_ok=True)

    with open(app.get_disk_data_path(), 'w+') as f:
        f.write(json.dumps(app.get_data_to_cache()))


def fill_icon_path(app: ArchPackage, icon_paths: List[str], only_exact_match: bool):
    ends_with = re.compile(r'.+/{}\.(png|svg)$'.format(app.name), re.IGNORECASE)

    for path in icon_paths:
        if ends_with.match(path):
            app.icon_path = path
            return

    if not only_exact_match:
        pkg_icons_path = pacman.list_icon_paths({app.name})

        if pkg_icons_path:
            app.icon_path = pkg_icons_path[0]


def set_icon_path(app: ArchPackage, icon_name: str = None):
    installed_icons = pacman.list_icon_paths(app.name)

    if installed_icons:
        exact_match = re.compile(r'.+/{}\..+$'.format(icon_name.split('.')[0] if icon_name else app.name))
        for icon_path in installed_icons:
            if exact_match.match(icon_path):
                app.icon_path = icon_path
                break


def save(pkgname: str, mirror: str):
    app = ArchPackage(name=pkgname, mirror=mirror)
    desktop_files = pacman.list_desktop_entries({pkgname})

    if desktop_files:
        if len(desktop_files) > 1:
            exact_match = [f for f in desktop_files if f.endswith('{}.desktop'.format(pkgname))]
            to_parse = exact_match[0] if exact_match else desktop_files[0]
        else:
            to_parse = desktop_files[0]

        app.desktop_entry = to_parse

        with open(to_parse) as f:
            desktop_entry = f.read()

        for field in RE_DESKTOP_ENTRY.findall(desktop_entry):
            if field[0] == 'Exec':
                app.command = field[1].strip()
            elif field[0] == 'Icon':
                app.icon_path = field[1].strip()

        if app.icon_path and '/' not in app.icon_path:  # if the icon full path is not defined
            set_icon_path(app, app.icon_path)
    else:
        bin_paths = pacman.list_bin_paths({pkgname})

        if bin_paths:
            if len(bin_paths) > 1:
                exact_match = [p for p in bin_paths if p.endswith('/' + pkgname)]
                app.command = exact_match[0] if exact_match else bin_paths[0]
            else:
                app.command = bin_paths[0]

        set_icon_path(app)

    Path(app.get_disk_cache_path()).mkdir(parents=True, exist_ok=True)

    with open(app.get_disk_data_path(), 'w+') as f:
        f.write(json.dumps(app.get_data_to_cache()))


def save_several(pkgnames: Set[str], mirror: str, overwrite: bool = True) -> int:
    to_cache = {n for n in pkgnames if overwrite or not os.path.exists(ArchPackage.disk_cache_path(n, mirror))}
    desktop_files = pacman.list_desktop_entries(to_cache)

    no_desktop_files = {}

    to_write = []
    if desktop_files:
        desktop_matches, no_exact_match = {}, set()
        for pkg in to_cache:  # first try to find exact matches
            ends_with = re.compile('.+/{}.desktop$'.format(pkg), re.IGNORECASE)

            for f in desktop_files:
                if ends_with.match(f):
                    desktop_matches[pkg] = f
                    break

            if pkg not in desktop_matches:
                no_exact_match.add(pkg)

        if no_exact_match:  # check every not matched app individually
            for pkg in no_exact_match:
                entries = pacman.list_desktop_entries({pkg})

                if entries:
                    desktop_matches[pkg] = entries[0]

        if not desktop_matches:
            no_desktop_files = to_cache
        else:
            if len(desktop_matches) != len(to_cache):
                no_desktop_files = {p for p in to_cache if p not in desktop_matches}

            pkgs, apps_icons_noabspath = [], []

            for pkgname, file in desktop_matches.items():
                p = ArchPackage(name=pkgname, mirror=mirror)
                p.desktop_entry = file

                with open(file) as f:
                    desktop_entry = f.read()

                for field in RE_DESKTOP_ENTRY.findall(desktop_entry):
                    if field[0] == 'Exec':
                        p.command = field[1].strip()
                    elif field[0] == 'Icon':
                        p.icon_path = field[1].strip()

                        if p.icon_path and '/' not in p.icon_path:  # if the icon full path is not defined
                            apps_icons_noabspath.append(p)

                pkgs.append(p)

            if apps_icons_noabspath:
                icon_paths = pacman.list_icon_paths({app.name for app in apps_icons_noabspath})

                if icon_paths:
                    for p in apps_icons_noabspath:
                        fill_icon_path(p, icon_paths, False)

            for p in pkgs:
                to_write.append(p)

    if no_desktop_files:
        pkgs = {ArchPackage(name=n, mirror=mirror) for n in no_desktop_files}
        bin_paths = pacman.list_bin_paths(no_desktop_files)

        if bin_paths:
            for p in pkgs:
                ends_with = re.compile(r'.+/{}$'.format(p.name), re.IGNORECASE)

                for path in bin_paths:
                    if ends_with.match(path):
                        p.command = path
                        break

        icon_paths = pacman.list_icon_paths(no_desktop_files)

        if icon_paths:
            for p in pkgs:
                fill_icon_path(p, icon_paths, only_exact_match=True)

        for p in pkgs:
            to_write.append(p)

    if to_write:
        for p in to_write:
            write(p)
        return len(to_write)
    return 0

