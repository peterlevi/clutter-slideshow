#!/usr/bin/env python3
# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-
### BEGIN LICENSE
# Copyright (c) 2015, Peter Levi <peterlevi@peterlevi.com>
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License version 3, as published
# by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranties of
# MERCHANTABILITY, SATISFACTORY QUALITY, or FITNESS FOR A PARTICULAR
# PURPOSE.  See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program.  If not, see <http://www.gnu.org/licenses/>.
### END LICENSE
import json
import logging
import optparse
import os
import random
import signal
import sys
import time
from multiprocessing import Process, Queue

from .AttrDict import AttrDict

# fmt: off
import gi  # isort:skip
gi.require_version('Gtk', '3.0')
gi.require_version('GtkClutter', '1.0')
from gi.repository import GtkClutter  # isort:skip

GtkClutter.init(sys.argv)

from gi.repository import Gtk, Gdk, GObject, Clutter, GLib, GdkPixbuf, Cogl  # isort:skip

Gtk.init(sys.argv)
# fmt: on


IMAGE_TYPES = (".jpg", ".jpeg", ".png", ".bmp")

SECONDS = 6
FADE = 0.5
ZOOM = 0.2
PAN = 0.05

random.seed(time.time())
logging.basicConfig()


def is_image(filename):
    return os.path.isfile(filename) and filename.lower().endswith(IMAGE_TYPES)


class VarietySlideshow:
    def current_monitors_help(self):
        result = "Your current monitors are: "
        screen = Gdk.Screen.get_default()
        for i in range(0, screen.get_n_monitors()):
            geo = screen.get_monitor_geometry(i)
            result += (", " if i > 0 else "") + "%d - %s, %dx%d" % (
                i + 1,
                screen.get_monitor_plug_name(i),
                geo.width,
                geo.height,
            )
        return result

    def load_options(self):
        if "--defaults" in sys.argv:
            self.options = AttrDict()
            return

        try:
            configdir = os.path.expanduser("~/.config/variety/")
            configfile = os.path.join(configdir, "variety_slideshow.json")
            with open(configfile, encoding="utf8") as f:
                self.options = AttrDict(json.load(f))
        except:
            self.options = AttrDict()

    def save_options(self):
        try:
            configdir = os.path.expanduser("~/.config/variety/")
            try:
                os.makedirs(configdir)
            except:
                pass
            configfile = os.path.join(configdir, "variety_slideshow.json")
            with open(configfile, "w", encoding="utf8") as f:
                json.dump(self.options, f, ensure_ascii=False)
        except:
            logging.exception("Could not save options:")

    def parse_options(self):
        """Support for command line options"""
        usage = """%prog [options] [list of images and/or image folders]
Starts a slideshow using the given images and/or image folders. Options are automatically saved, and reused next time you start the slideshow."""
        parser = optparse.OptionParser(usage=usage)

        parser.add_option(
            "-s",
            "--seconds",
            action="store",
            type="float",
            dest="seconds",
            default=self.options.get("seconds", SECONDS),
            help="Interval in seconds between image changes.\n"
            "Default is %s.\n"
            "Float, at least 0.1." % SECONDS,
        )
        parser.add_option(
            "--fade",
            action="store",
            type="float",
            dest="fade",
            default=self.options.get("fade", FADE),
            help="Fade duration, as a fraction of the interval.\n"
            "Default is 0.4, i.e. 0.4 * 6 = 2.4 seconds.\n"
            "Float, between 0 and 1.\n"
            "0 disables fade.",
        )
        parser.add_option(
            "--zoom",
            action="store",
            type="float",
            dest="zoom",
            default=self.options.get("zoom", ZOOM),
            help="How much to zoom in or out images, as a ratio of their size.\n"
            "Default is %s.\n"
            "Float, at least 0.\n"
            "0 disables zoom." % ZOOM,
        )
        parser.add_option(
            "--pan",
            action="store",
            type="float",
            dest="pan",
            default=self.options.get("pan", PAN),
            help="How much to pan images sideways, as a ratio of screen size.\n"
            "Default is %s.\n"
            "Float, at least 0.\n"
            "0 disables pan." % PAN,
        )

        parser.add_option(
            "--sort",
            action="store",
            type="string",
            dest="sort",
            default=self.options.get("sort", "random"),
            help="""
In what order to cycle the files. Possible values are:
random - random order (Default);
keep - keep order, specified on the commandline (only useful when specifying files, not folders);
name - sort by folder name, then by filename;
date - sort by file date;""",
        )

        parser.add_option(
            "--order",
            action="store",
            dest="sort_order",
            default=self.options.get("sort_order", "asc"),
            help="Sort order: asc/ascending (this is the default), or desc/descending",
        )

        parser.add_option(
            "--monitor",
            action="store",
            type="int",
            dest="monitor",
            default=self.options.get("monitor", 1),
            help="On which monitor to run - 1, 2, etc. up to the number of monitors.\n"
            + self.current_monitors_help(),
        )

        parser.add_option(
            "--mode",
            action="store",
            dest="mode",
            default=self.options.get("mode", "fullscreen"),
            help="Window mode: possible values are 'fullscreen', 'maximized', 'desktop', 'window' and 'undecorated'. "
            "Default is fullscreen.",
        )

        parser.add_option(
            "--title",
            action="store",
            type="string",
            dest="title",
            default=self.options.get("title", "Variety Slideshow"),
            help="Window title",
        )

        parser.add_option(
            "--hide-from-taskbar",
            action="store_true",
            dest="hide_from_taskbar",
            default=self.options.get("hide_from_taskbar", False),
            help="If specified, we will instruct the window manager to not show a button for "
            "Variety Slideshow in the taskbar or the application switcher. Some WMs might "
            "ignore this hint.",
        )

        parser.add_option(
            "--dont-hide-from-taskbar",
            action="store_false",
            dest="hide_from_taskbar",
            default=self.options.get("hide_from_taskbar", False),
            help="Used to reverse the effect of a previous run with --hide-from-taskbar. "
            "If specified, we will NOT instruct the window manager to not show a button for "
            "Variety Slideshow in the taskbar or the application switcher and will persist this as "
            "the new default behavior.",
        )

        parser.add_option(
            "--defaults",
            action="store_true",
            dest="defaults",
            help="Do not load saved options, use defaults instead. "
            "You can still specify commandline parameters to override them.",
        )

        parser.add_option(
            "--quit-on-motion",
            action="store_true",
            dest="quit_on_motion",
            help="Should mouse motion stop the slideshow, like a screensaver?",
        )

        parser.add_option(
            "--aspect-ratio-target",
            action="store",
            dest="ar_target",
            default=self.options.get("ar_target", "max"),
            help="Try to fit/shrink pictures to screen ('min') or fill screen ('max')" 
            "Default is 'max'.",
        )

        cmd_options, args = parser.parse_args(sys.argv)
        self.options.update(vars(cmd_options))
        if "defaults" in self.options:
            del self.options["defaults"]
        if len(args) > 1:
            self.options.files_and_folders = args[1:]
        if "files_and_folders" not in self.options:
            self.options.files_and_folders = ["/usr/share/backgrounds/"]

        if self.options.seconds < 0.1:
            parser.error("Seconds should be at least 0.1")
        self.interval = self.options.seconds * 1000

        if self.options.fade < 0 or self.options.fade > 1:
            parser.error("Fade should be between 0 and 1")
        self.fade_time = self.interval * self.options.fade

        if self.options.zoom < 0:
            parser.error("Zoom should be at least 0")

        if self.options.pan < 0:
            parser.error("Pan should be at least 0")

        self.options.mode = self.options.mode.lower()
        if self.options.mode not in (
            "fullscreen",
            "maximized",
            "desktop",
            "window",
            "undecorated",
            "desktop",
        ):
            parser.error(
                "Window mode: possible values are "
                "'fullscreen', 'maximized', 'desktop', 'window' and 'undecorated'"
            )

        self.parser = parser

    def prepare_file_queues(self):
        self.queued = []
        self.files = []
        self.error_files = set()
        self.cursor = 0

        for arg in self.options.files_and_folders:
            path = os.path.abspath(os.path.expanduser(arg))
            if is_image(path):
                self.files.append(path)

            elif os.path.isdir(path):
                for root, dirnames, filenames in os.walk(path):
                    for filename in filenames:
                        full_path = os.path.join(root, filename)
                        if is_image(full_path):
                            self.files.append(full_path)
                        if len(self.files) > 2000:
                            break
                    else:
                        continue
                    break
                else:
                    continue
                break

        if not self.files:
            self.parser.error("You should specify some files or folders")

        sort = self.options.sort.lower()
        if sort == "keep":
            pass
        elif sort == "name":
            self.files.sort()
        elif sort == "date":
            self.files.sort(key=os.path.getmtime)
        else:
            random.shuffle(self.files)

        if self.options.sort_order.lower().startswith("desc"):
            self.files.reverse()

    def get_next_file(self):
        if not self.running:
            return None
        if len(self.queued):
            return self.queued.pop(0)
        else:
            if self.error_files == set(self.files):
                logging.error("Could not find any non-corrupt images, exiting.")
                self.quit()
                return None

            f = self.files[self.cursor]
            self.cursor = (self.cursor + 1) % len(self.files)
            if f in self.error_files:
                return self.get_next_file()
            else:
                return f

    def queue(self, filename):
        self.queued.append(filename)

    def connect_signals(self):
        # Connect signals
        def on_button_press(*args):
            if self.current_mode == "fullscreen" and not self.mode_was_changed:
                self.quit()

        def on_motion(*args):
            if (
                self.options.quit_on_motion
                and self.current_mode == "fullscreen"
                and not self.mode_was_changed
            ):
                self.quit()

        def on_key_press(widget, event):
            if self.current_mode == "fullscreen" and not self.mode_was_changed:
                self.quit()
                return

            key = Gdk.keyval_name(event.keyval)

            if key == "Escape":
                self.quit()

            elif key in ("f", "F", "F11"):
                if self.current_mode == "desktop":
                    return
                if self.current_mode == "fullscreen":
                    self.current_mode = "window"
                    self.window.unfullscreen()
                else:
                    self.current_mode = "fullscreen"
                    self.window.fullscreen()
                self.mode_was_changed = True
                GObject.timeout_add(200, self.go_next)

            elif key in ("d", "D"):
                if self.current_mode == "undecorated":
                    self.current_mode = "window"
                    self.window.set_decorated(True)
                else:
                    self.current_mode = "undecorated"
                    self.window.set_decorated(False)

        self.window.connect("delete-event", self.quit)
        self.stage.connect("destroy", self.quit)
        self.stage.connect("key-press-event", on_key_press)
        self.stage.connect("button-press-event", on_button_press)
        self.stage.connect("motion-event", on_motion)

    def run(self):
        self.running = True

        self.window = Gtk.Window()

        self.load_options()  # loads from config file
        self.parse_options()  # parses the command-line arguments, these take precedence over the saved config
        self.save_options()
        self.prepare_file_queues()

        self.window.set_title(self.options.title)
        self.screen = self.window.get_screen()

        self.embed = GtkClutter.Embed()
        self.window.add(self.embed)
        self.embed.set_visible(True)

        self.stage = self.embed.get_stage()
        self.stage.set_color(Clutter.Color.get_static(Clutter.StaticColor.BLACK))
        if self.options.mode == "fullscreen":
            self.stage.hide_cursor()

        self.texture = Clutter.Texture.new()
        self.next_texture = None
        self.prev_texture = None
        self.data_queue = Queue()

        self.connect_signals()

        self.will_enlarge = random.choice((True, False))

        self.window.resize(600, 400)
        self.move_to_monitor(self.options.monitor)

        self.current_mode = self.options.mode
        self.mode_was_changed = False
        if self.options.mode == "fullscreen":
            self.window.fullscreen()
            self.window.set_skip_taskbar_hint(True)
        elif self.options.mode == "maximized":
            self.window.maximize()
        elif self.options.mode == "desktop":
            self.window.maximize()
            self.window.set_decorated(False)
            self.window.set_keep_below(True)

            # ensure window will get deiconified (i.e. unminimized) after "Show Desktop" button/shortcut
            def _window_state_changed(window, event, *args):
                if event.new_window_state & Gdk.WindowState.ICONIFIED:
                    self.window.deiconify()
                    self.window.present()

            self.window.connect("window-state-event", _window_state_changed)

        elif self.options.mode == "undecorated":
            self.window.set_decorated(False)

        if self.options.hide_from_taskbar:
            self.window.set_skip_taskbar_hint(True)

        def after_show(*args):
            def f():
                self.move_to_monitor(self.options.monitor)
                self.prepare_next_data()
                self.go_next()

            GObject.timeout_add(200, f)

        self.window.connect("show", lambda *args: GObject.idle_add(after_show))
        self.window.show()
        Gtk.main()

    def quit(self, *args):
        logging.info("Exiting...")
        self.running = False
        Gtk.main_quit()

    def move_to_monitor(self, i):
        i = max(1, min(i, self.screen.get_n_monitors()))
        rect = self.screen.get_monitor_geometry(i - 1)
        self.window.move(
            rect.x + (rect.width - self.window.get_size()[0]) / 2,
            rect.y + (rect.height - self.window.get_size()[1]) / 2,
        )

    def go_next(self, *args):
        if not self.running:
            return
        try:
            if hasattr(self, "next_timeout"):
                GObject.source_remove(self.next_timeout)
                delattr(self, "next_timeout")

            image_data = self.data_queue.get(True, timeout=1)
            if not isinstance(image_data, tuple):
                if image_data:
                    logging.info("Error in %s, skipping it" % image_data)
                    self.error_files.add(image_data)
                self.prepare_next_data()
                return self.go_next()

            self.next_texture = self.create_texture(image_data)
            target_size, target_position = self.initialize_pan_and_zoom(self.next_texture)

            self.stage.add_actor(self.next_texture)
            self.toggle(self.texture, False)
            self.toggle(self.next_texture, True)

            self.start_pan_and_zoom(self.next_texture, target_size, target_position)

            if self.prev_texture:
                self.prev_texture.destroy()
            self.prev_texture = self.texture
            self.texture = self.next_texture

            self.next_timeout = GObject.timeout_add(
                int(self.interval), self.go_next, priority=GLib.PRIORITY_HIGH
            )
            self.prepare_next_data()
        except:
            logging.exception("Oops, exception in next, rescheduling:")
            self.next_timeout = GObject.timeout_add(100, self.go_next, priority=GLib.PRIORITY_HIGH)

    def get_ratio_to_screen(self, texture):
        if (self.options.ar_target == 'max'):
            return max(
                self.stage.get_width() / texture.get_width(),
                self.stage.get_height() / texture.get_height(),
            )
        else:
            return min(
                self.stage.get_width() / texture.get_width(),
                self.stage.get_height() / texture.get_height(),
            )

    def prepare_next_data(self):
        filename = self.get_next_file()
        if not filename:
            self.data_queue.put(None)
            return

        def _prepare(filename):
            os.nice(20)
            max_w = self.stage.get_width() * (1 + 2 * self.options.zoom)
            max_h = self.stage.get_height() * (1 + 2 * self.options.zoom)

            try:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(filename, max_w, max_h, True)
                data = (
                    pixbuf.get_pixels(),
                    pixbuf.get_has_alpha(),
                    pixbuf.get_width(),
                    pixbuf.get_height(),
                    pixbuf.get_rowstride(),
                    4 if pixbuf.get_has_alpha() else 3,
                )
                self.data_queue.put(data)
            except:
                logging.exception("Could not open file %s" % filename)
                self.data_queue.put(filename)

        p = Process(target=_prepare, args=(filename,))
        p.daemon = True
        p.start()

    def create_texture(self, image_data):
        data = tuple(image_data) + (Clutter.TextureFlags.NONE,)
        texture = Clutter.Texture.new()
        texture.set_from_rgb_data(*data)
        texture.set_opacity(0)
        texture.set_keep_aspect_ratio(True)
        return texture

    def initialize_pan_and_zoom(self, texture):
        self.will_enlarge = not self.will_enlarge

        pan_px = max(self.stage.get_width(), self.stage.get_height()) * self.options.pan
        rand_pan = lambda: random.choice((-1, 1)) * (pan_px + pan_px * random.random())
        zoom_factor = (1 + self.options.zoom) * (1 + self.options.zoom * random.random())

        scale = self.get_ratio_to_screen(texture)
        base_w, base_h = texture.get_width() * scale, texture.get_height() * scale

        safety_zoom = 1 + self.options.pan / 2 if self.options.zoom > 0 else 1

        small_size = base_w * safety_zoom, base_h * safety_zoom
        big_size = base_w * safety_zoom * zoom_factor, base_h * safety_zoom * zoom_factor
        small_position = (
            -(small_size[0] - self.stage.get_width()) / 2,
            -(small_size[1] - self.stage.get_height()) / 2,
        )
        big_position = (
            -(big_size[0] - self.stage.get_width()) / 2 + rand_pan(),
            -(big_size[1] - self.stage.get_height()) / 2 + rand_pan(),
        )

        if self.will_enlarge:
            initial_size, initial_position = small_size, small_position
            target_size, target_position = big_size, big_position
        else:
            initial_size, initial_position = big_size, big_position
            target_size, target_position = small_size, small_position

        # set initial size
        texture.set_size(*initial_size)
        texture.set_position(*initial_position)

        return target_size, target_position

    def start_pan_and_zoom(self, texture, target_size, target_position):
        # start animating to target size
        texture.save_easing_state()
        texture.set_easing_mode(Clutter.AnimationMode.LINEAR)
        texture.set_easing_duration(self.interval + self.fade_time)
        texture.set_size(*target_size)
        texture.set_position(*target_position)

    def toggle(self, texture, visible):
        texture.set_reactive(visible)
        texture.save_easing_state()
        texture.set_easing_mode(
            Clutter.AnimationMode.EASE_OUT_SINE if visible else Clutter.AnimationMode.EASE_IN_SINE
        )
        texture.set_easing_duration(self.fade_time)
        texture.set_opacity(255 if visible else 0)
        if visible:
            self.stage.raise_child(texture, None)


def main():
    # Ctrl-C
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    signal.signal(signal.SIGTERM, signal.SIG_DFL)
    signal.signal(signal.SIGQUIT, signal.SIG_DFL)

    VarietySlideshow().run()


if __name__ == "__main__":
    main()
