#!/usr/bin/env python
#
# JSON.py
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston,
# MA  02111-1307  USA
#
# Author:   Thorsten Sick <thorsten.sick@avira.com> from Avira
#           (developed for the iTES Project http://ites-project.org)

import logging
import datetime
import os
import json

try:
    from StringIO import StringIO
except ImportError:
    from io import StringIO

from .Mapper import Mapper
from .compatibility import thug_unicode

log = logging.getLogger("Thug")


class JSON(object):
    def __init__(self, thug_version, provider = False):
        self._tools = ({
                        'id'          : 'json-log',
                        'Name'        : 'Thug',
                        'Version'     : thug_version,
                        'Vendor'      : None,
                        'Organization': 'The Honeynet Project',
                       }, )

        self.associated_code = None
        self.object_pool     = None
        self.signatures      = list()
        self.cached_data     = None
        self.provider        = provider

        self.data = {
                        "url"         : None,
                        "timestamp"   : str(datetime.datetime.now()),
                        "logtype"     : "json-log",
                        "thug"        : {
                                        "version"            : thug_version,
                                        "personality" : {
                                            "useragent"      : log.ThugOpts.useragent
                                            },
                                        "plugins" : {
                                            "acropdf"        : self.get_vuln_module("acropdf"),
                                            "javaplugin"     : self.get_vuln_module("_javaplugin"),
                                            "shockwaveflash" : self.get_vuln_module("shockwave_flash")
                                            },
                                        "options" : {
                                            "local"          : log.ThugOpts.local,
                                            "nofetch"        : log.ThugOpts.no_fetch,
                                            "proxy"          : log.ThugOpts._proxy,
                                            "events"         : log.ThugOpts.events,
                                            "delay"          : log.ThugOpts.delay,
                                            "referer"        : log.ThugOpts.referer,
                                            "timeout"        : log.ThugOpts.timeout,
                                            "threshold"      : log.ThugOpts.threshold,
                                            "extensive"      : log.ThugOpts.extensive,
                                            },
                                        },
                        "behavior"    : [],
                        "code"        : [],
                        "files"       : [],
                        "connections" : [],
                        "locations"   : [],
                        "exploits"    : [],
                        "classifiers" : [],
                    }

    @property
    def json_enabled(self):
        return log.ThugOpts.json_logging or 'json' in log.ThugLogging.formats or self.provider

    def get_vuln_module(self, module):
        disabled = getattr(log.ThugVulnModules, "%s_disabled" % (module, ), True)
        if disabled:
            return "disabled"

        return getattr(log.ThugVulnModules, module)

    def fix(self, data):
        """
        Fix encoding of data

        @data  data to encode properly
        """
        try:
            enc = log.Encoding.detect(data)
            return data.decode(enc['encoding']).replace("\n", "").strip()
        except: #pylint:disable=bare-except
            return thug_unicode(data).replace("\n", "").strip()

    def make_counter(self, p):
        _id = p
        while True:
            yield _id
            _id += 1

    def set_url(self, url):
        if not self.json_enabled:
            return

        self.data["url"] = self.fix(url)

    def add_code_snippet(self, snippet, language, relationship, method = "Dynamic Analysis"):
        if not self.json_enabled:
            return

        self.data["code"].append({"snippet"      : self.fix(snippet),
                                  "language"     : self.fix(language),
                                  "relationship" : self.fix(relationship),
                                  "method"       : self.fix(method)})

    def log_connection(self, source, destination, method, flags = None):
        """
        Log the connection (redirection, link) between two pages

        @source        The origin page
        @destination   The page the user is made to load next
        @method        Link, iframe, .... that moves the user from source to destination
        @flags         Additional information flags. Existing are: "exploit"
        """
        if not self.json_enabled:
            return

        if flags is None:
            flags = dict()

        if "exploit" in flags and flags["exploit"]:
            self.add_behavior_warn("[Exploit]  %s -- %s --> %s" % (source,
                                                                   method,
                                                                   destination, ))
        else:
            self.add_behavior_warn("%s -- %s --> %s" % (source,
                                                        method,
                                                        destination,))

        self.data["connections"].append({"source"       : self.fix(source),
                                         "destination"  : self.fix(destination),
                                         "method"       : method,
                                         "flags"        : flags})

    def log_location(self, url, data, flags = None):
        """
        Log file information for a given url

        @url    URL we fetched data from
        @data   File dictionary data
                    Keys:
                        - content     Content
                        - md5         MD5 checksum
                        - sha256      SHA-256 checksum
                        - fsize       Content size
                        - ctype       Content type (whatever the server says it is)
                        - mtype       Calculated MIME type

        @flags  Additional information flags (known flags: "error")
        """
        if not self.json_enabled:
            return

        if flags is None:
            flags = dict()

        self.data["locations"].append({"url"          : self.fix(url),
                                       "content-type" : data.get("ctype", None),
                                       "md5"          : data.get("md5", None),
                                       "sha256"       : data.get("sha256", None),
                                       "flags"        : flags,
                                       "size"         : data.get("fsize", None),
                                       "mimetype"     : data.get("mtype", None)})

    def log_exploit_event(self, url, module, description, cve = None, data = None):
        """
        Log file information for a given url

        @url            URL where this exploit occured
        @module         Module/ActiveX Control, ... that gets exploited
        @description    Description of the exploit
        @cve            CVE number (if available)
        """
        if not self.json_enabled:
            return

        self.data["exploits"].append({"url"         : self.fix(url),
                                      "module"      : module,
                                      "description" : description,
                                      "cve"         : cve,
                                      "data"        : data})

    def log_classifier(self, classifier, url, rule, tags):
        """
        Log classifiers matching for a given url

        @classifier     Classifier name
        @url            URL where the rule match occurred
        @rule           Rule name
        @tags           Rule tags
        """
        if not self.json_enabled:
            return

        item = {"classifier" : classifier,
                "url"        : self.fix(url),
                "rule"       : rule,
                "tags"       : tags}

        if item not in self.data["classifiers"]:
            self.data["classifiers"].append(item)

    def add_behavior(self, description = None, cve = None, method = "Dynamic Analysis"):
        if not self.json_enabled:
            return

        if not cve and not description:
            return

        self.data["behavior"].append({"description" : self.fix(description),
                                      "cve"         : self.fix(cve),
                                      "method"      : self.fix(method),
                                      "timestamp"   : str(datetime.datetime.now())})

    def add_behavior_warn(self, description = None, cve = None, method = "Dynamic Analysis"):
        if not self.json_enabled:
            return

        self.add_behavior(description, cve, method)

    def log_file(self, data, url = None, params = None):
        if not self.json_enabled:
            return

        self.data["files"].append(data)

    def export(self, basedir):
        if not self.json_enabled:
            return

        output = StringIO()
        json.dump(self.data, output, sort_keys = False, indent = 4)
        if log.ThugOpts.json_logging and log.ThugOpts.file_logging:
            logdir = os.path.join(basedir, "analysis", "json")
            log.ThugLogging.store_content(logdir, 'analysis.json', output.getvalue())

            m = Mapper(logdir)
            m.add_data(self.data)
            m.write_svg()

        self.cached_data = output

    def get_json_data(self, basedir):
        if self.cached_data:
            return self.cached_data.getvalue()

        return None
