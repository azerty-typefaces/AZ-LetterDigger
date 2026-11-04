"""AZ Letter Digger — digs up optimal test words for type design.

General Plugin shell: adds a Window ▸ AZ Toolkit item (with the bundled
assets/az-icon.pdf art) that opens the AZ Letter Digger window. All real work lives
in azletterdigger_ui (window/Glyphs glue) and azletterdigger_engine (pure
scoring logic).
"""

import traceback

import objc
from AppKit import NSImage, NSMenu, NSMenuItem, NSWorkspace
from Foundation import NSURL, NSLog
from GlyphsApp import WINDOW_MENU, Glyphs
from GlyphsApp.plugins import GeneralPlugin

MENU_ICON_HEIGHT = 16.0  # points; standard macOS menu-item icon height


# ──────────────────────────────────────────────────────────────────────────────
# The plugin's face
# ──────────────────────────────────────────────────────────────────────────────
# Template image: the black art is inked with the text colour, so it reads in
# light mode, dark mode and on a highlighted row.

AZ_ICON_FILE = "assets/az-icon.pdf"
_AZ_ICON_CACHE: dict = {}


def _az_icon(point_size: float = 14.0):
    """The bundled plugin icon as a template NSImage `point_size` tall, or None.

    Cached per size: an NSImage is mutable, so two sizes can't share one object.
    """
    cached = _AZ_ICON_CACHE.get(point_size)
    if cached is not None:
        return cached
    try:
        import os

        # The art sits in the bundle's Resources/, but the module asking for it
        # may be a package DEEPER than that (azkeyring/sidebar.py), so walk up.
        folder = os.path.dirname(os.path.abspath(__file__))
        path = None
        for _ in range(3):
            candidate = os.path.join(folder, AZ_ICON_FILE)
            if os.path.exists(candidate):
                path = candidate
                break
            folder = os.path.dirname(folder)
        if path is None:
            return None
        image = NSImage.alloc().initByReferencingFile_(path)
        if image is None or not image.isValid():
            return None
        # size() is an NSSize struct, not a tuple.
        natural = image.size()
        if natural.height:
            image.setSize_((natural.width * point_size / natural.height, point_size))
        image.setTemplate_(True)
        _AZ_ICON_CACHE[point_size] = image
        return image
    except Exception:
        return None


# ──────────────────────────────────────────────────────────────────────────────
# Window ▸ AZ Toolkit
# ──────────────────────────────────────────────────────────────────────────────
# One "AZ Toolkit" item in the Window menu, every AZ plugin a child ("AZ "
# dropped), the site link last. The first plugin to load builds it; the rest
# insert themselves alphabetically.

AZ_TOOLKIT_MENU_TITLE = "AZ Toolkit"
AZ_TOOLKIT_SITE_TITLE = "More AZ plugins…"
AZ_TOOLKIT_SITE_URL = "https://azerty-typefaces.com"
# Shared toolkit tag for AZ plugins; Letter Digger's child-item tag is distinct.
AZ_TOOLKIT_MENU_TAG = 0x415A544B  # AZTK
AZ_LETTER_DIGGER_MENU_TAG = 0x415A4C44  # AZLD


class AZLetterDigger(GeneralPlugin):
    @objc.python_method
    def settings(self):
        self.name = "AZ Letter Digger"
        self.window = None
        print("__AZLetterDigger", self)

    @objc.python_method
    def start(self):
        self._install_menu()

        # Tab in Glyphs ▸ Settings ▸ AZ Toolkit: show/hide the dice, its colour.
        try:
            from azletterdigger_settings import register_preferences_pane

            register_preferences_pane(
                lambda: self.window if self.window is not None and self.window.is_open() else None
            )
        except Exception:
            print(f"AZ Letter Digger settings error:\n{traceback.format_exc()}")

        # Bridge: other plugins (AZ Classifier) can ask AZ Letter Digger to proof a tag
        # group by posting this notification with {"tag": <title>}.
        from AppKit import NSNotificationCenter

        NSNotificationCenter.defaultCenter().addObserver_selector_name_object_(
            self, "digTagNotification:", "com.hugojourdan.AZLetterDigger.dig", None
        )

    @objc.python_method
    def _install_menu(self):
        window_menu = Glyphs.menu[WINDOW_MENU].submenu()
        print("__window_menu", window_menu)
        parent = window_menu.itemWithTag_(AZ_TOOLKIT_MENU_TAG)
        if parent is None:
            submenu = NSMenu.alloc().initWithTitle_(AZ_TOOLKIT_MENU_TITLE)
            parent = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                AZ_TOOLKIT_MENU_TITLE, None, ""
            )
            parent.setTag_(AZ_TOOLKIT_MENU_TAG)
            parent.setSubmenu_(submenu)
            try:
                icon = NSImage.imageWithSystemSymbolName_accessibilityDescription_(
                    "wrench.and.screwdriver", AZ_TOOLKIT_MENU_TITLE
                )
                if icon is not None:
                    icon.setTemplate_(True)
                    icon.setSize_((14.0, 14.0))
                    parent.setImage_(icon)
            except Exception:
                import traceback
                print(traceback.format_exc())

            site_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                AZ_TOOLKIT_SITE_TITLE, "openAZSite:", ""
            )
            # GeneralPlugin instances live for the app session, so self remains
            # a valid target even though NSMenuItem doesn't retain its target.
            site_item.setTarget_(self)
            submenu.addItem_(NSMenuItem.separatorItem())
            submenu.addItem_(site_item)
            window_menu.addItem_(parent)

        submenu = parent.submenu()
        item = submenu.itemWithTag_(AZ_LETTER_DIGGER_MENU_TAG)
        if item is not None:
            return

        title = self.name[3:] if self.name.startswith("AZ ") else self.name
        item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            title, self.showWindow_, ""
        )
        item.setTag_(AZ_LETTER_DIGGER_MENU_TAG)
        item.setTarget_(self)
        icon = _az_icon(MENU_ICON_HEIGHT)
        if icon is not None:
            item.setImage_(icon)

        # Walk only to find the alphabetical insertion point above the footer.
        insert_at = submenu.numberOfItems()
        for index, existing in enumerate(submenu.itemArray()):
            if existing.isSeparatorItem() or str(existing.title() or "") > title:
                insert_at = index
                break
        submenu.insertItem_atIndex_(item, insert_at)

    def openAZSite_(self, sender):
        NSWorkspace.sharedWorkspace().openURL_(NSURL.URLWithString_(AZ_TOOLKIT_SITE_URL))

    def digTagNotification_(self, notification):
        try:
            info = notification.userInfo() or {}
            tag = str(info.get("tag", ""))
            self.showWindow_(None)
            if self.window is not None and tag:
                self.window.dig_tag(tag)
        except Exception:
            Glyphs.showMacroWindow()
            print(f"AZ Letter Digger dig-tag error:\n{traceback.format_exc()}")

    def showWindow_(self, sender):
        try:
            # Lazy import keeps app launch fast and surfaces import errors
            # in the Macro panel instead of silently disabling the plugin.
            from azletterdigger_ui import AZLetterDiggerWindow

            if self.window is None or not self.window.is_open():
                self.window = AZLetterDiggerWindow()
            else:
                self.window.bring_to_front()
        except Exception:
            Glyphs.showMacroWindow()
            print(f"AZ Letter Digger error:\n{traceback.format_exc()}")

    @objc.python_method
    def __file__(self):
        """Please leave this method unchanged"""
        return __file__
