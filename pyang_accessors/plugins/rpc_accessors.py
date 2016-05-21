#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
"""
import re
import optparse

from pyang import plugin

from pyang_accessors import __version__
from pyang_accessors.generators import RPCGenerator

__author__ = "Anderson Bravalheri"
__copyright__ = "andersonbravalheri@gmail.com"
__license__ = "mozilla"

FILENAME_REGEX = re.compile(r"^(.*?)(\@(\d{4}-\d{2}-\d{2}))?\.(\w+)$")


def pyang_plugin_init():
    plugin.register_plugin(RPCAccessorsPlugin())


class RPCAccessorsPlugin(plugin.PyangPlugin):

    def add_opts(self, optparser):
        """Add command line options"""
        optgrp = optparser.add_option_group(
            '`pyang-accessors` plugin specific options')
        optgrp.add_options([
            optparse.make_option(
                '--output-module-suffix', default='interface',
                help=(
                    'The generated module will have this string added to:\n'
                    ' - the original module name (if not provided)\n'
                    ' - the original module namespace (if not provided)\n'
                    ' - the original prefix name (if not provided)\n'
                )
            ),
            optparse.make_option(
                '--output-module-name', default=None,
                help='The generated module will have this name'
            ),
            optparse.make_option(
                '--output-module-namespace', default=None,
                help='The generated module will have this namespace'
            ),
            optparse.make_option(
                '--output-module-prefix', default=None,
                help='The generated module will have this prefix'
            ),
        ])

    def add_output_format(self, fmts):
        """Register output formats handled by plugin"""

        self.multiple_modules = False
        fmts['rpc-accessors'] = self

    def emit(self, ctx, modules, fp):
        """Generate YANG/YIN file with RPC definitions"""

        options = ctx.opts
        name = options.output_module_name
        suffix = options.output_module_suffix
        generator_options = {
            'namespace': options.output_module_namespace,
            'prefix': options.output_module_prefix,
        }
        output_name = ctx.opts.outfile

        if output_name:
            match = FILENAME_REGEX.search(output_name)
            if match is not None:
                name = match.group(1)

        generator_options['name'] = name

        generator = RPCGenerator(ctx, suffix=suffix)
        out = generator.transform(modules[0], **generator_options)

        out.dump(fp)