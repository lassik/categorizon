#! /usr/bin/env python3

# IDEA: If file with same name already exists in target directory, but file contents are different, then append a number to new filename.
# IDEA: Recurse into subdirectories in some reasonable manner.
# IDEA: Handle zipfiles in some reasonable manner.
# IDEA: Cleanup filenames (URL-decode, remove weird chars, extra whitespace, punctuation).
# IDEA: Find duplicate files, move extra copies to trash.
# IDEA: Auto-convert .ps files to .pdf using some command-line tool.
# IDEA: Auto-convert .svg to .png (keep both files)
# IDEA: Lowercase filename extension .PDF -> .pdf

import argparse
import configparser
import errno
import os
import sys
import tempfile
from subprocess import Popen

import pyglet
import send2trash


def color(hex6):
    return ((0xff & (hex6 >> 16)), (0xff & (hex6 >> 8)), (0xff & hex6))


PROGNAME = "categorizon"
FONT = "Helvetica"
FILENAME_FONT_SIZE = 20
PREVIEW_FONT_SIZE = 20
BUTTON_FONT_SIZE = 16
WINDOW_WIDTH = 1200
WINDOW_HEIGHT = 700
BUTTON_WIDTH = 150
BUTTON_HEIGHT = 30
BUTTON_FUDGE_FACTOR = 16
BUTTONS_PER_ROW = 4
GAP = 10

BUTTON_BACK_COLOR = color(0xaaaaaa)
BUTTON_TEXT_COLOR = color(0xffffff)
FILENAME_TEXT_COLOR = color(0x999999)


def has_ext(basename, exts):
    return os.path.splitext(basename)[1].lower().replace(".", "") in exts.split()


def dirnames(dirpath):
    return list(sorted(os.listdir(dirpath), key=str.lower))


def exists_or_symlink(path):
    try:
        os.lstat(path)
    except FileNotFoundError:
        return False
    return True


def fill_rectangle(x, y, w, h, rgb):
    pyglet.graphics.draw(
        4,
        pyglet.gl.GL_QUADS,
        ("v2f", [x, y, x + w, y, x + w, y - h, x, y - h]),
        ("c3B", rgb * 4),
    )


def draw_image_from_file(filename):
    image = pyglet.image.load(filename)
    scale_x = g_window.width / image.width
    scale_y = g_window.height / image.height
    scale = min(scale_x, scale_y)
    sprite = pyglet.sprite.Sprite(image)
    sprite.update(scale=scale)
    sprite.draw()


def load_to_player(srcpath):
    global g_player
    if g_player:
        g_player.next_source()
        g_player.delete()
    g_player = None
    if srcpath:
        g_player = pyglet.media.Player()


class Grid:
    def __init__(self, action_text_pairs):
        self.texts, self.actions = zip(*action_text_pairs)

    def get_button_xy(self, i):
        grid_width = BUTTONS_PER_ROW * BUTTON_WIDTH + (BUTTONS_PER_ROW - 1) * GAP
        x = (i % BUTTONS_PER_ROW) * (BUTTON_WIDTH + GAP)
        y = (i // BUTTONS_PER_ROW) * (BUTTON_HEIGHT + GAP)
        x = g_window.width - grid_width + x
        y = g_window.height - y
        return (x, y)

    def get_button_index_at_xy(self, x, y):
        for i in range(len(self.texts)):
            xbut, ybut = self.get_button_xy(i)
            if xbut < x < xbut + BUTTON_WIDTH and ybut - BUTTON_HEIGHT < y < ybut:
                return i
        return None

    def call_button_action_at_xy(self, x, y):
        i = self.get_button_index_at_xy(x, y)
        if i is None:
            return None
        return self.actions[i]()

    def draw(self):
        for i, text in enumerate(self.texts):
            x, y = self.get_button_xy(i)
            fill_rectangle(x, y, BUTTON_WIDTH, BUTTON_HEIGHT, BUTTON_BACK_COLOR)
            pyglet.text.Label(
                text,
                font_name=FONT,
                font_size=BUTTON_FONT_SIZE,
                color=BUTTON_TEXT_COLOR + (255,),
                x=x + BUTTON_WIDTH // 2,
                y=y - BUTTON_FUDGE_FACTOR,
                anchor_x="center",
                anchor_y="center",
            ).draw()


class Category:

    CATNAME = None

    def __init__(self, srcpath):
        self.srcpath = srcpath
        self.fulldir = g_targets[self.CATNAME]
        load_to_player(None)

    @classmethod
    def file_matches(self, srcpath):
        return False

    def draw_preview(self, x, y):
        pass


class Code(Category):

    CATNAME = "code"

    @classmethod
    def file_matches(self, srcpath):
        return has_ext(srcpath, "c cpp el h hpp hs java js lisp lua pl py rb scm sh")


class Document(Category):

    CATNAME = "documents"

    @classmethod
    def file_matches(self, srcpath):
        return has_ext(srcpath, "azw3 doc epub mobi pdf ps rtf text txt")

    def draw_preview_pdf(self, x, y):
        with tempfile.TemporaryDirectory(PROGNAME) as tmpdir:
            tmpfile = os.path.join(tmpdir, "tmp.png")
            tmpstem = os.path.splitext(tmpfile)[0]
            sub = Popen(
                ["pdftoppm", self.srcpath, tmpstem, "-png", "-f", "1", "-singlefile"]
            )
            sub.communicate()
            if sub.returncode == 0:
                draw_image_from_file(tmpfile)

    def draw_preview(self, x, y):
        if has_ext(self.srcpath, "pdf"):
            return self.draw_preview_pdf(x, y)
        return pyglet.text.Label(
            open(self.srcpath, "rb").read(200).decode("utf-8", "ignore"),
            font_name=FONT,
            font_size=PREVIEW_FONT_SIZE,
            x=x,
            y=y,
        )


class Picture(Category):

    CATNAME = "pictures"

    @classmethod
    def file_matches(self, srcpath):
        return has_ext(srcpath, "bmp gif jpeg jpg jpg_large png svg tif tiff")

    def draw_preview(self, x, y):
        if has_ext(self.srcpath, "svg"):
            return
        draw_image_from_file(self.srcpath)


class Video(Category):

    CATNAME = "videos"

    @classmethod
    def file_matches(self, srcpath):
        return has_ext(srcpath, "avi flv mkv mov mp4 ogv srt webm wmv")

    def draw_preview(self, x, y):
        tex = g_player.get_texture()
        if tex:
            tex.blit(0, 0)

    def __init__(self, srcpath):
        super().__init__(srcpath)
        load_to_player(self.srcpath)


class Audio(Category):

    CATNAME = "audio"

    @classmethod
    def file_matches(self, srcpath):
        return has_ext(srcpath, "flac m4a mp3 ogg opus wav")

    def __init__(self, srcpath):
        super().__init__(srcpath)
        load_to_player(self.srcpath)


CATEGORIES = Category.__subclasses__()


def file_category(srcpath):
    for cat in CATEGORIES:
        if cat.file_matches(srcpath):
            return cat(srcpath)
    return None


def move_file_to_dst_subdir(dst_subdir):
    def foo():
        assert g_cat
        dststem, dstext = os.path.splitext(os.path.basename(g_cat.srcpath))
        dstext = {".jpg": ".jpg_large"}.get(dstext, dstext)
        dstfulldir = os.path.join(g_cat.fulldir, dst_subdir)
        dstpath = os.path.join(dstfulldir, dststem + dstext)
        print(dstpath)
        assert not exists_or_symlink(dstpath)
        os.rename(g_cat.srcpath, dstpath)
        next_file()

    return foo


def move_file_to_dst_root():
    return move_file_to_dst_subdir("")


def move_file_to_trash():
    assert g_cat
    print("Moving to trash:", g_cat.srcpath)
    send2trash.send2trash(g_cat.srcpath)
    next_file()


def play_file():
    assert g_player
    g_player.next_source()
    g_player.queue(pyglet.media.load(g_cat.srcpath))
    g_player.play()


g_targets = {
    "audio": os.path.expanduser("~/Music"),
    "code": os.path.expanduser("~/src"),
    "documents": os.path.expanduser("~/Documents"),
    "pictures": os.path.expanduser("~/Pictures"),
    "videos": os.path.expanduser("~/Videos"),
}

apars = argparse.ArgumentParser()
apars.add_argument("srcdir", nargs="?", default=os.path.expanduser("~/Downloads"))
args = apars.parse_args()

DSTDIR = os.path.expanduser("~/persist/public")
config = configparser.ConfigParser()
config.read(os.path.expanduser("~/.config/{}.ini".format(PROGNAME)))
for k, v in config["targets"].items():
    g_targets[k] = os.path.expanduser(v)
print(repr(g_targets))

g_remaining_files = [os.path.join(args.srcdir, name) for name in dirnames(args.srcdir)]

g_window = pyglet.window.Window(width=WINDOW_WIDTH, height=WINDOW_HEIGHT)
g_filename_label = None
g_grid = None
g_cat = None
g_player = None


@g_window.event
def on_draw():
    g_window.clear()
    if g_cat:
        g_cat.draw_preview(10, 10)
    if g_filename_label:
        g_filename_label.draw()
    if g_grid:
        g_grid.draw()


@g_window.event
def on_mouse_press(x, y, button, modifiers):
    if g_grid:
        g_grid.call_button_action_at_xy(x, y)


def maybe_play_button():
    return [("PLAY", play_file)] if g_player else []


def next_file():
    global g_cat, g_grid, g_filename_label
    g_cat, g_grid, g_filename_label = None, None, None
    basename, srcpath = None, None
    while not g_cat and len(g_remaining_files) > 0:
        srcpath = g_remaining_files.pop(0)
        basename = os.path.basename(srcpath)
        g_cat = file_category(srcpath)
    print()
    if not g_cat:
        print("NO MORE FILES")
        return
    print("PRESENTING FILE:", basename)
    g_filename_label = pyglet.text.Label(
        basename,
        font_name=FONT,
        font_size=FILENAME_FONT_SIZE,
        color=FILENAME_TEXT_COLOR + (255,),
        x=0,
        y=g_window.height - FILENAME_FONT_SIZE,
    )
    g_grid = Grid(
        [
            ("SKIP", next_file),
            ("TO TRASH", move_file_to_trash),
            ("TO ROOT", move_file_to_dst_root()),
        ]
        + maybe_play_button()
        + [
            (name, move_file_to_dst_subdir(name))
            for name in dirnames(os.path.join(g_cat.fulldir))
            if os.path.isdir(os.path.join(g_cat.fulldir, name))
        ]
    )


next_file()
pyglet.app.run()
