#!/usr/bin/env python3
import hashlib
import os
import re
import shutil
import sys

from src.date import Date
from src.exif import Exif
from src.printer import Printer
from src.logger import Logger

printer = Printer()
logger = Logger()
ignored_files = (
  ".DS_Store", 
  "Thumbs.db", 
  "ZbThumbnail.info",
)

class Phockup():
    def __init__(self, input, output, **args):
        input = os.path.expanduser(input)
        output = os.path.expanduser(output)

        if input.endswith(os.path.sep):
            input = input[:-1]
        if output.endswith(os.path.sep):
            output = output[:-1]

        self.input = input
        self.output = output
        self.dir_format = args.get('dir_format', os.path.sep.join(['%Y', '%m', '%d']))
        self.move = args.get('move', False)
        self.link = args.get('link', False)
        self.original_filenames = args.get('original_filenames', False)
        self.date_regex = args.get('date_regex', None)
        self.timestamp = args.get('timestamp', False)
        self.output_log = args.get('output_log', False)
        self.path_root = args.get('path_root', '')
        self.date_field = args.get('date_field', False)
        self.dry_run = args.get('dry_run', False)
        self.check_directories()
        self.walk_directory()

        if self.output_log:
            log_name = os.path.split(self.input)[1] + '.pickle'
            printer.line(f'Saving log to {log_name}')
            logger.save_to_disk(os.path.join(self.output, log_name))
        

    def check_directories(self):
        """
        Check if input and output directories exist.
        If input does not exists it exits the process
        If output does not exists it tries to create it or exit with error
        """
        if not os.path.isdir(self.input) or not os.path.exists(self.input):
            printer.error('Input directory "%s" does not exist or cannot be accessed' % self.input)
            return
        if not os.path.exists(self.output):
            printer.line('Output directory "%s" does not exist, creating now' % self.output)
            try:
                if not self.dry_run:
                    os.makedirs(self.output)
            except Exception:
                printer.error('Cannot create output directory. No write access!')

    def walk_directory(self):
        """
        Walk input directory recursively and call process_file for each file except the ignored ones
        """
        for root, _, files in os.walk(self.input):
            files.sort()
            for filename in files:
                if filename in ignored_files:
                    checksum = self.checksum(os.path.join(root, filename))
                    logger.add_entry(checksum, os.path.join(root, filename), '', Logger.ACTION_IGNORE)
                    continue

                file = os.path.join(root, filename)
                self.process_file(file)

    def checksum(self, file):
        """
        Calculate checksum for a file.
        Used to match if duplicated file name is actually a duplicated file
        """
        block_size = 65536
        sha256 = hashlib.sha256()
        with open(file, 'rb') as f:
            for block in iter(lambda: f.read(block_size), b''):
                sha256.update(block)
        return sha256.hexdigest()

    def is_image_or_video(self, mimetype):
        """
        Use mimetype to determine if the file is an image or video
        """
        pattern = re.compile('^(image/.+|video/.+|application/vnd.adobe.photoshop)$')
        if pattern.match(mimetype):
            return True
        return False

    def get_output_dir(self, date, file):
        """
        Generate output directory path based on the extracted date and formatted using dir_format
        If date is missing from the exifdata the file is going to "unknown" directory
        unless user included a regex from filename or uses timestamp
        """
        toplevel = 'archive'

        if date and not date['guessing']:
            try:
                path = [self.output, toplevel, date['date'].date().strftime(self.dir_format)]
            except:
                # keep relative path (from src root dir) , .e.g.
                # root_dir/rel/path/bla.pdf ==> dst_dir/unknown/rel/path/bla.pdf
                repl = self.path_root if self.path_root else self.input
                if not repl.endswith(os.path.sep):
                    repl = repl + os.path.sep
                rel_path_from_root = os.path.dirname(os.path.abspath(file)).replace(repl, '')
                
                path = [self.output, 'unknown', rel_path_from_root]

        else:
            # keep relative path (from src root dir) , .e.g.
            # root_dir/rel/path/bla.pdf ==> dst_dir/unknown/rel/path/bla.pdf
            repl = self.path_root if self.path_root else self.input
            if not repl.endswith(os.path.sep):
                repl = repl + os.path.sep
            rel_path_from_root = os.path.dirname(os.path.abspath(file)).replace(repl, '')
            
            path = [self.output, 'unknown', rel_path_from_root]

        fullpath = os.path.sep.join(path)

        if not os.path.isdir(fullpath) and not self.dry_run:
            os.makedirs(fullpath)

        return fullpath

    def get_file_name(self, file, date):
        """
        Generate file name based on exif data unless it is missing or
        original filenames are required. Then use original file name
        """
        if self.original_filenames:
            return os.path.basename(file)

        try:
            filename = [
                '%04d' % date['date'].year,
                '%02d' % date['date'].month,
                '%02d' % date['date'].day,
                '_',
                '%02d' % date['date'].hour,
                '%02d' % date['date'].minute,
                '%02d' % date['date'].second,
            ]

            if date['subseconds']:
                filename.append(date['subseconds'])

            return ''.join(filename) + os.path.splitext(file)[1]
        except:
            return os.path.basename(file)

    def process_file(self, file):
        """
        Process the file using the selected strategy
        If file is .xmp skip it so process_xmp method can handle it
        """
        if str.endswith(file, '.xmp'):
            return None

        printer.line(file, True)

        output, target_file_name, target_file_path = self.get_file_name_and_path(file)

        suffix = 1
        target_file = target_file_path
        
        if self.output_log:
            checksum = self.checksum(file)
        else:
            checksum = ''

        while True:
            if os.path.isfile(target_file):
                if not self.output_log:
                    checksum = self.checksum(file)
                if checksum == self.checksum(target_file):
                    logger.add_entry(checksum, file, target_file, Logger.ACTION_SKIP)
                    printer.line(' => skipped, duplicated file %s' % target_file)
                    break
            else:
                if self.move and not self.dry_run:
                    try:
                        shutil.move(file, target_file)
                        logger.add_entry(checksum, file, target_file, Logger.ACTION_MOVE)
                    except FileNotFoundError:
                        printer.line(' => skipped, no such file or directory')
                        break
                elif self.link and not self.dry_run:
                    os.link(file, target_file)
                    logger.add_entry(checksum, file, target_file, Logger.ACTION_LINK)
                elif not self.dry_run:
                    try:
                        shutil.copy2(file, target_file)
                        logger.add_entry(checksum, file, target_file, Logger.ACTION_COPY)
                    except FileNotFoundError:
                        printer.line(' => skipped, no such file or directory')
                        break

                printer.line(' => %s' % target_file)
                self.process_xmp(file, target_file_name, suffix, output)
                break

            suffix += 1
            target_split = os.path.splitext(target_file_path)
            target_file = "%s-%d%s" % (target_split[0], suffix, target_split[1])

    def get_file_name_and_path(self, file):
        """
        Returns target file name and path
        """
        exif_data = Exif(file).data()
        if exif_data and 'MIMEType' in exif_data and self.is_image_or_video(exif_data['MIMEType']):
            date = Date(file).from_exif(exif_data, self.timestamp, self.date_regex, self.date_field)
            output = self.get_output_dir(date, file)
            target_file_name = self.get_file_name(file, date).lower()
            if not self.original_filenames:
                target_file_name = target_file_name.lower()
            target_file_path = os.path.sep.join([output, target_file_name])
        else:
            output = self.get_output_dir(False, file)
            target_file_name = os.path.basename(file)
            target_file_path = os.path.sep.join([output, target_file_name])

        return output, target_file_name, target_file_path

    def process_xmp(self, file, file_name, suffix, output):
        """
        Process xmp files. These are meta data for RAW images
        """
        xmp_original_with_ext = file + '.xmp'
        xmp_original_without_ext = os.path.splitext(file)[0] + '.xmp'

        suffix = '-%s' % suffix if suffix > 1 else ''

        if os.path.isfile(xmp_original_with_ext):
            xmp_original = xmp_original_with_ext
            xmp_target = '%s%s.xmp' % (file_name, suffix)
        elif os.path.isfile(xmp_original_without_ext):
            xmp_original = xmp_original_without_ext
            xmp_target = '%s%s.xmp' % (os.path.splitext(file_name)[0], suffix)
        else:
            xmp_original = None
            xmp_target = None

        if xmp_original:
            xmp_path = os.path.sep.join([output, xmp_target])
            printer.line('%s => %s' % (xmp_original, xmp_path))

            if not self.dry_run:
                if self.move:
                    shutil.move(xmp_original, xmp_path)
                elif self.link:
                    os.link(xmp_original, xmp_path)
                else:
                    shutil.copy2(xmp_original, xmp_path)
