#!/usr/bin/env python
"""Class to load and parse """
import logging
import psycopg2
import csv
import inspect
import sys
import collections
import dateparser
import json
import datetime
from psycopg2.extras import Json
from cvpy.common import check_environment as ce

simple_attrs = (
    "cases|deaths|presumptive|recovered|tested|hospitalized|negative"
    "|severe|monitored|no_longer_monitored|pending|active|inconclusive"
    "|quarantined"
).split("|")


class CSVLoader(object):

    """Loads and parse CSV files into the database"""

    def __init__(self, db, schema='staging',
                 logger=logging.getLogger(ce('PY_LOGGER', 'main')), dry_run=0):
        """Initialize CSV Loader.

        :logger: logger instance, defaults to PY_LOGGER

        """
        csv.field_size_limit(sys.maxsize)

        self._logger = logger
        self._dry_run = dry_run
        self.db = db
        self.schema = schema

    def create_attribute(self, dataset, attr,
                         name=f"FIXME: name autogenerated by {sys.argv[0]}",
                         meta=None, ignore_duplicate=False):
        """Inserts new attribute name ignoring KeyViolation.
        Will add % to meta if 'percent' is in the name.

        :attr: attribute name
        :meta: attribute metadata
        """

        # add '%' to metadata if the name contains 'percent'
        if 'percent' in attr:
            if meta is None:
                meta = {}
            meta['type'] = '%'

        # FIXME: do an explicit check on attribute presence possibly in memory
        # FIXME: check for if metadata is compatible
        try:
            self.db.cur.execute(
                f"INSERT INTO" +
                f"    {self.schema}.attributes(dataset_id, attr, name, meta)" +
                f" VALUES (%s, %s, %s, %s)",
                (dataset, attr, name, Json(meta) if meta else None))
        except psycopg2.IntegrityError as e:
            if ignore_duplicate:
                self.db.con.rollback()
            else:
                raise e
        else:
            self.db.con.commit()

    def mk_attr_name(self, row, *arg_parts, check_prc=False):
        """assembles attribute clean name from multiple part,
        creates attrribute extension

        :row: OrderedDist with the CSV row
        :*parts: parts of the name being created,
                 names prepended with '=' will be treated as literals,
                 all others will be used as index to row
        :check_prc: if true 'percent' column will be checked and the
                    name and ext modified accrodibgly
        :attr_ext: attribute extension will be created and/or appended
                   from attribute name
        :returns: attr_name

        """

        parts = list(arg_parts)

        for i, part in enumerate(parts):
            if part.startswith('='):
                parts[i] = part[1:].strip().lower()
            else:
                # remove excessive spaces in the attribute names
                parts[i] = " ".join(row[part].strip().lower().split())

        if check_prc and row['percent']:
            if row['percent'].strip().lower() == 'yes':
                parts.append('percent')
            else:
                self._logger.warning(
                    f"The value of 'percent' column is not Yes or empty"
                    f"{row['percent']}")

        attr_name = '_'.join(parts)

        return attr_name

    @staticmethod
    def same_ign_none(l1, l2):
        """Compares 2 lists element by element ignoring positions with None values

        :l1: 1st list
        :l2: 2nd list
        :returns: True if all elements are the same, None values ignored

        """

        assert len(l1) == len(l2)

        return all([
            l1[i] == l2[i]
            for i, _ in enumerate(l1)
            if not l1[i] is None and not l2[i] is None
        ])

    @staticmethod
    def lno():
        """current line number (for debugging)
        :returns: file name and line number

        """
        return __name__ + ':' + str(inspect.currentframe().f_back.f_lineno)

    def store_stav(self, scrape_id, geounit_id, vtime, attr, val,
                   csv_row=None, csv_col=None):
        """Store value tuple in the database

        :scrape_id: identifier for the scrape
        :geounit_id: identifier for the region
        :valid_time: time of observation
        :attr: name of the attributes
        :val: value of the attribute (text)
        :meta: attribute metadata (percent, UoM, etc.)
        :csv_row, csv_col: back reference to original CSV for debugging,
                           will be stored in the parser column

        """

        try:

            # FIXME: in the code I presume that all metadata is inherited from
            # the attributes table
            self.db.cur.execute(f"INSERT INTO {self.schema}.stav( "
                                f"scrape_id, geounit_id, vtime, attr, val, "
                                f"csv_row, csv_col) "
                                f"VALUES (%s, %s, %s, %s, %s, %s, %s)",
                                (scrape_id, geounit_id, vtime, attr, val,
                                 csv_row, csv_col))

        except psycopg2.IntegrityError as e:
            # this is needed to collect errors while processing all files
            _line_no = inspect.currentframe().f_back.f_lineno
            self._logger.warning(f"IntegrityError in file {csv_row} from"
                                 f" {__name__}:{_line_no},"
                                 f" failure on value={val}: {e}")
            self.db.con.rollback()

        else:
            self.db.con.commit()

    def load(self, csv_stream=None, fname=None, op='append', logger=None,
             rows=[]):
        """loads data from csv_stream to db

        :csv_stream: python stream with the CSV file
        :db: database object
        :op: operation (append, new, replace)

        """

        if not logger:
            logger = self._logger

        _ts = datetime.datetime.now().isoformat()
        logger.info("Loading of {} started at {}".format(fname, _ts))

        if not csv_stream:
            csv_stream = open(fname, "r", encoding='utf-8-sig',
                              errors='replace')
        csvr = csv.DictReader(csv_stream)

        # reset file-level variables
        simpl_vals_prev = []
        id_vals_prev = []  # set of values that identifies a scrape
        row_prev = None    # a copy of the previous row
        group_row = 0
        group_type = group_hospital_name = None  # group_type_prev =
        provider = vendor = dataset = None
        current_range = 0
        missing_columns = []

        if self._dry_run:
            logger.info("...dry run...")
            return

        if op == 'replace':
            # FIXME: transaction isolation --- the count of deleted
            # data points is not correct when multiple processes are running
            self.db.cur.execute(f"SELECT count(*) from {self.schema}.stav")
            cnt = self.db.cur.fetchone()[0]
            self.db.cur.execute(f"DELETE FROM {self.schema}.scrapes "
                                f"WHERE csv_file = %s",
                                (fname,))
            self.db.cur.execute(f"SELECT count(*) from {self.schema}.stav")
            cnt -= self.db.cur.fetchone()[0]
            logger.info(f'Removed {cnt} data points previously loaded from '
                        'this file')
            self.db.con.commit()
        elif op == 'new':
            # load only CSVs not already loaded
            self.db.cur.execute(f"SELECT * FROM {self.schema}.scrapes "
                                f"WHERE csv_file = %s",
                                (fname,))
            if self.db.cur.rowcount:
                logger.info(f"{fname} already loaded, skipping...")
                return

        for row_no, raw_row in enumerate(csvr):
            # row_no is not the same as csvr.line_num

            # cleanup empty strings and lower case keys
            row = collections.OrderedDict()
            for k, v in raw_row.items():
                if len(v.strip()) > 0:
                    row[k.lower()] = v.strip()
                else:
                    row[k.lower()] = None

            # actions before the 1st row
            if row_no == 0:
                # check for essential columns once per file
                try:
                    for c in ('access_time', 'state'):
                        _ = row[c]
                except KeyError:
                    logger.warning(f"Column '{c}' not found in {fname},"
                                   " file skipped")
                    break

            # fill columns missing in manual scrapes
            if not row['access_time']:
                logger.warning(f"Value in 'access_time' is None, skipping row"
                               f"{fname}:{row_no}")
                continue
            if 'provider' not in row or row['provider'] == 'state':
                row['provider'] = 'doe-covid19'
            if 'country' not in row:
                row['country'] = 'US'
            if 'other value' in row:
                row['other_value'] = row['other value']
                del row['other value']
            if 'quarantine' in row:
                row['quarantined'] = row['quarantine']
                del row['quarantine']

            if row_no == 0:
                # these are columns missing either in manually or
                # automatically scraped CSVs
                for c in ('resolution', 'no_longer_monitored', 'page',
                          'pending', 'quarantined', 'percent', 'county',
                          'other_value', 'region'):
                    if c not in row:
                        missing_columns.append(c)

                logger.warning(f"Missing columns: {missing_columns}")

            for c in missing_columns:
                row[c] = None

            # skip row if requestd
            if rows:
                crange = rows[current_range]
                if not (len(crange) == 1 and row_no == crange[0]
                        or row_no >= crange[0] and row_no <= crange[1]):
                    logger.info(f"\rSkipped CSV row {row_no}  ")
                    continue
                if len(crange) == 1 or row_no == crange[1]:
                    current_range += 1
                    if current_range >= len(rows):
                        logger.info("The rest of the file skipped")
                        break

            # skip all rows with all empty values
            if not any(row.values()):
                logger.warning(f"Skipped empty row in {fname}:{row_no}")
                continue

            # save provider, dataset, and vendor
            if row['provider'] != provider:
                provider = row['provider']
                try:
                    self.db.cur.execute(f"INSERT INTO {self.schema}.providers "
                                        "(provider_id) VALUES (%s)",
                                        (provider, ))
                except psycopg2.IntegrityError:
                    self.db.con.rollback()
                else:
                    self.db.con.commit()

                if provider == 'doe-covid19':
                    vendor = 'US^' + row['state']
                    dataset = vendor + ':COVID19'
                else:
                    vendor = dataset = provider

                try:
                    self.db.cur.execute(f"INSERT INTO {self.schema}.vendors "
                                        "(vendor_id, name) VALUES (%s, "
                                        "'FIXME: name autogenerated by "
                                        f"{__name__}')",
                                        (vendor,))
                except psycopg2.IntegrityError:
                    self.db.con.rollback()
                else:
                    self.db.con.commit()

                try:
                    self.db.cur.execute(f"INSERT INTO {self.schema}.datasets "
                                        f"(vendor_id, dataset_id, name) "
                                        f"VALUES (%s, %s, "
                                        "'FIXME: name autogenerated by "
                                        f"{__name__}')",
                                        (vendor, dataset))
                except psycopg2.IntegrityError:
                    self.db.con.rollback()
                else:
                    self.db.con.commit()

            # set times
            try:
                parsed_time = dateparser.parse(row['access_time'])
                if parsed_time is None:
                    raise ValueError()
                else:
                    row['access_time'] = parsed_time
            except ValueError as e:
                logger.warning(f"Unparseable time in 'access_time' "
                               f"{fname}:{row_no}, "
                               f"row skipped: {row['access_time']}, {e}")
                continue
            # extract day of the record, the logic
            #   * use 'updated' if avavilable
            #     * can be in jason format
            #     * if missing in some records use one found for the file
            #   * otherwise use access_time
            #  TODO: * if not avavilable extract from the file name
            valid_time = None
            if row['updated'] is None and id_vals_prev:
                # get valid time from the previos row
                valid_time = id_vals_prev[2]
            elif row['updated']:
                if row['updated'].strip().startswith('{'):
                    try:
                        jd = json.loads(row['updated'].replace("'", '"'))
                        valid_time = datetime.date(jd['year'], jd['month'],
                                                   jd['day'])
                    except json.decoder.JSONDecodeError as e:
                        logger.warning(f"Unparseable 'updated' JSON in "
                                       f"{fname}:{row_no}, "
                                       f"row skipped: {row['updated']}, {e}")
                        continue
                else:
                    try:
                        ts_for_valid_time = dateparser.parse(row['updated'])
                        if ts_for_valid_time is None:
                            raise ValueError()
                        else:
                            valid_time = ts_for_valid_time.date()
                    except ValueError as e:
                        logger.warning(f"Unparseable time in 'updated' "
                                       f"{fname}:{row_no}, "
                                       f"row skipped: {row['updated']}, {e}")
                        continue
            # no good valid_time
            if valid_time is None:
                valid_time = row['access_time'].date()

            # insert scrapes
            if not row['url']:
                logger.warning(f"Missing URL in {fname}:{row_no},"
                               f" row skipped: {row}")
                continue
            self.db.cur.execute(f"SELECT scrape_id "
                                f"FROM {self.schema}.scrapes "
                                f"WHERE provider_id = %s "
                                f"    AND uri = %s "
                                f"    AND scraped_ts = %s",
                                (row['provider'], row['url'],
                                 row['access_time']))
            if not self.db.cur.rowcount:  # this means "not found"
                self.db.cur.execute(f"INSERT INTO "
                                    f"{self.schema}.scrapes(provider_id, "
                                    f"     uri, dataset_id, scraped_ts, doc,"
                                    f"     csv_file, csv_row) "
                                    f"VALUES (%s, %s, %s, %s, %s, %s, %s) "
                                    f"RETURNING scrape_id",
                                    (row['provider'], row['url'], dataset,
                                     row['access_time'], row['page'], fname,
                                     row_no))
                self.db.con.commit()
            scrape_id = self.db.cur.fetchone()[0]

            # detect row group type based on values in columns
            if group_type == 'other.hospital':
                # this is another kind of groupping
                # FIXME: assumption here is that hospital groups go until
                # the end of the file
                if row['other'] == 'HospitalName':
                    group_hospital_name = row['other_value']
                    group_row = 0
                    continue
            elif row['age_range']:
                #   1.  age group
                #   1.1 includes age-sex subgroup
                group_type = 'age'
                if row['sex']:
                    group_type = 'age.sex'
                elif row['other']:
                    group_type = 'age.other'
            elif row['sex']:
                #   2.  sex group (does not include rows in age group)
                group_type = 'sex'
                if row['other']:
                    group_type = 'sex.other'
            elif row['other'] and row['other'] == 'HospitalName':
                group_type = 'other.hospital'
                group_hospital_name = row['other_value']
                group_row = 0
                continue
            else:
                #   0.  no group
                group_type = None
            # future groups
            #   3.  other group
            #   4.  ? hospital group

            # 'region' is assmebled from country-state-county
            geounit_id = "^".join([
                row[c].upper()
                for c in ('country', 'state', 'county')
                if row[c]
            ])
            if row['region']:
                geounit_id += "$" + row['region']
            if group_type == 'other.hospital':
                geounit_id += "$" + group_hospital_name
                row['resolution'] = 'hospital'
            try:
                self.db.cur.execute(f"INSERT INTO {self.schema}.geounits "
                                    "(geounit_id, resolution) VALUES (%s, %s)",
                                    (geounit_id, row['resolution']))
            except psycopg2.IntegrityError:
                self.db.con.rollback()
            else:
                self.db.con.commit()

            # make a copy of the whole row
            id_vals = [scrape_id, geounit_id, valid_time]
            simpl_vals = id_vals + [row[r] for r in simple_attrs]
            if row_no == 0:  # 1st row in the CSV file
                id_vals_prev = id_vals
                simpl_vals_prev = simpl_vals
                row_prev = row

            # reset group row count if
            #  * group type has changed
            #  * new file
            #  * new scrape
            #  * new region
            #  * new time
            #  * no group
            if id_vals != id_vals_prev or group_type is None:
                # or group_type != group_type_prev:
                group_row = 0
            else:
                group_row += 1

            # special case: age groups
            if group_type and group_type.startswith('age'):

                # collect values from age_* columns
                for attr in [a for a in row.keys() if row[a]]:
                    if attr.startswith("age_") and attr != 'age_range':

                        attr_name = self.mk_attr_name(row, "=age", 'age_range',
                                                      '='+attr[4:])
                        self.create_attribute(dataset, attr_name,
                                              ignore_duplicate=True)
                        self.store_stav(scrape_id, geounit_id, valid_time,
                                        attr_name, row[attr], row_no, attr)

                if group_type == 'age':
                    for attr in [a for a in simple_attrs if row[a]]:
                        if group_row == 0:
                            # load simple_attrs value from the 1st row for
                            # all subtypes of group 'age'
                            attr_name = self.mk_attr_name(row, '='+attr,
                                                          check_prc=True)
                            self.create_attribute(dataset, attr_name,
                                                  ignore_duplicate=True)
                            self.store_stav(scrape_id, geounit_id, valid_time,
                                            attr, row[attr], row_no, attr)
                        elif row[attr] != row_prev[attr]:
                            logger.warning(f"None-repeating attribute '{attr}'"
                                           f"({row[attr]} vs {row_prev[attr]})"
                                           f" in group '{group_type}'"
                                           f" in {fname}:{row_no} " +
                                           self.lno())

                elif group_type == 'age.sex':
                    # process age-specific sex here
                    for attr in [a for a in row.keys() if row[a]]:
                        if attr.startswith("sex_"):

                            attr_name = self.mk_attr_name(row, "=age",
                                                          "age_range", 'sex',
                                                          '='+attr[4:])
                            self.create_attribute(dataset, attr_name,
                                                  ignore_duplicate=True)
                            self.store_stav(scrape_id, geounit_id, valid_time,
                                            attr_name, row[attr], row_no, attr)

                        elif attr in simple_attrs:
                            # this is the case when both age_range and sex
                            # then simple_attrs are applied to age_range
                            if group_row == 0:

                                attr_name = self.mk_attr_name(row, "=age",
                                                              'age_range',
                                                              '='+attr,
                                                              check_prc=True)
                                self.create_attribute(dataset, attr_name,
                                                      ignore_duplicate=True)
                                self.store_stav(scrape_id, geounit_id,
                                                valid_time, attr, row[attr],
                                                row_no, attr)

                            elif row[attr] != row_prev[attr]:
                                # skip repeating values in other
                                # than the 1st row
                                logger.warning(f"None-repeating attribute "
                                               f"'{attr}' ({row[attr]} vs "
                                               f"{row_prev[attr]}) in group "
                                               f"'{group_type}' in "
                                               f"{fname}:{row_no} " +
                                               self.lno())
                                logger.warning(f"prev: {simpl_vals_prev}")
                                logger.warning(f"curr: {simpl_vals}")

                elif group_type == 'age.other':
                    # process 'other' groupings like comorbidities
                    if row['other_value']:
                        try:
                            float(row['other_value'])
                            # treat values in other_value and simple_attrs
                            # as a normal row
                            if group_row == 0:
                                for attr in [a
                                             for a in simple_attrs
                                             if row[a]
                                             ]:
                                    attr_name = self.mk_attr_name(row,
                                                                  '='+attr,
                                                                  check_prc=True)
                                    self.create_attribute(dataset, attr_name,
                                                          ignore_duplicate=True)
                                    self.store_stav(scrape_id, geounit_id,
                                                    valid_time, attr_name,
                                                    row[attr], row_no, attr)

                                attr_name = self.mk_attr_name(row, '=age',
                                                              'age_range',
                                                              'other')
                                self.create_attribute(dataset, attr_name,
                                                      ignore_duplicate=True)
                                self.store_stav(scrape_id, geounit_id,
                                                valid_time, attr_name,
                                                row['other_value'], row_no,
                                                'other_value')

                            elif not self.same_ign_none(simpl_vals,
                                                        simpl_vals_prev):
                                logger.warning(f"None-repeating attribute in "
                                               f"group '{group_type}' in "
                                               f"{fname}:{row_no} " +
                                               self.lno())
                                logger.warning(f"prev: {simpl_vals_prev}")
                                logger.warning(f"curr: {simpl_vals}")

                        except ValueError:
                            # treat other_value as a mofifier simple attributes
                            for attr in [a for a in simple_attrs if row[a]]:

                                attr_name = self.mk_attr_name(row, '=age',
                                                              'age_range',
                                                              'other',
                                                              'other_value',
                                                              '='+attr,
                                                              check_prc=True)
                                self.create_attribute(dataset, attr_name,
                                                      ignore_duplicate=True)
                                self.store_stav(scrape_id, geounit_id,
                                                valid_time, attr_name,
                                                row[attr], row_no, attr)
                    else:
                        # other_value is empty, treta the content of 'other'
                        # as a modifier for simple_attrs
                        for attr in [a for a in simple_attrs if row[a]]:

                            attr_name = self.mk_attr_name(row, '=age',
                                                          'age_range',
                                                          'other', '='+attr,
                                                          check_prc=True)
                            self.create_attribute(dataset, attr_name,
                                                  ignore_duplicate=True)
                            self.store_stav(scrape_id, geounit_id, valid_time,
                                            attr_name, row[attr], row_no, attr)

                else:
                    logger.critical(f"BUG: Unknown age subgroup {group_type}")
                    raise ValueError(f"BUG: Unknown age subgroup {group_type}")

            # special case: sex
            elif group_type and group_type.startswith('sex'):

                for attr in [a for a in row.keys() if row[a]]:
                    if attr.startswith("sex_"):

                        attr_name = self.mk_attr_name(row, "=sex", 'sex',
                                                      '='+attr[4:])
                        self.create_attribute(dataset, attr_name,
                                              ignore_duplicate=True)
                        self.store_stav(scrape_id, geounit_id, valid_time,
                                        attr_name, row[attr], row_no, attr)

                if group_type == 'sex':
                    for attr in [a for a in simple_attrs if row[a]]:
                        if group_row == 0:
                            # load simple_attrs value from the 1st row for
                            # all subtypes of group 'age'
                            attr_name = self.mk_attr_name(row, '='+attr,
                                                          check_prc=True)
                            self.create_attribute(dataset, attr_name,
                                                  ignore_duplicate=True)
                            self.store_stav(scrape_id, geounit_id, valid_time,
                                            attr, row[attr], row_no, attr)
                        elif row[attr] != row_prev[attr]:
                            logger.warning(f"None-repeating attribute '{attr}'"
                                           f" in group '{group_type}' in "
                                           f"{fname}:{row_no} " + self.lno())

                elif group_type == 'sex.other':

                    if row['other_value']:
                        try:
                            float(row['other_value'])
                            # treat other_value as a value for attribute
                            # defined in column 'other'
                            if group_row == 0:
                                for attr in [a
                                             for a in simple_attrs
                                             if row[a]
                                             ]:
                                    attr_name = self.mk_attr_name(row,
                                                                  '='+attr,
                                                                  check_prc=True)
                                    self.create_attribute(dataset, attr_name,
                                                          ignore_duplicate=True)
                                    self.store_stav(scrape_id, geounit_id,
                                                    valid_time, attr_name,
                                                    row[attr], row_no, attr)

                                attr_name = self.mk_attr_name(row, '=sex',
                                                              'sex', 'other')
                                self.create_attribute(dataset, attr_name,
                                                      ignore_duplicate=True)
                                self.store_stav(scrape_id, geounit_id,
                                                valid_time, attr_name,
                                                row['other_value'], row_no,
                                                'other_value')

                            elif not self.same_ign_none(simpl_vals,
                                                        simpl_vals_prev):
                                logger.warning(f"None-repeating attribute in "
                                               f"group '{group_type}' in "
                                               f"{fname}:{row_no} " +
                                               self.lno())
                                logger.warning(f"prev: {simpl_vals_prev}")
                                logger.warning(f"curr: {simpl_vals}")

                        except Exception:

                            # look for corresponding values in other columns
                            attr_name = self.mk_attr_name(row, "=sex", "sex",
                                                          'other',
                                                          'other_value',
                                                          check_prc=True)
                            self.create_attribute(dataset, attr_name,
                                                  ignore_duplicate=True)
                            self.store_stav(scrape_id, geounit_id,
                                            valid_time, attr_name, row[attr],
                                            row_no, attr)

                    else:  # empty other_value

                        for attr in [a for a in simple_attrs if row[a]]:

                            attr_name = self.mk_attr_name(row, '=sex', 'sex',
                                                          'other', '='+attr,
                                                          check_prc=True)
                            self.create_attribute(dataset, attr_name,
                                                  ignore_duplicate=True)
                            self.store_stav(scrape_id, geounit_id, valid_time,
                                            attr_name, row[attr], row_no, attr)
                else:
                    logger.critical(f"BUG: Unknown age subgroup {group_type}")
                    raise ValueError(f"BUG: Unknown age subgroup {group_type}")

            elif group_type == 'other.hospital':

                if row['other_value']:
                    attr_name = self.mk_attr_name(row, 'other')
                    self.create_attribute(dataset, attr_name,
                                          ignore_duplicate=True)
                    self.store_stav(scrape_id, geounit_id, valid_time,
                                    attr_name, row['other_value'], row_no,
                                    'other_value')

                if group_row > 0 and not self.same_ign_none(simpl_vals,
                                                            simpl_vals_prev):
                    logger.warning(f"None-empty or none-repeating simple "
                                   f"attribute values in '{group_type}' "
                                   f"group in {fname}:{row_no} " + self.lno())
                    logger.warning(f"prev: {simpl_vals_prev}")
                    logger.warning(f"curr: {simpl_vals}")

            elif group_type is None:
                # special case: other outside of age and sex
                if row['other'] and row['other_value']:
                    try:
                        float(row['other_value'])
                        # treat 'other_value' as value

                        attr_name = self.mk_attr_name(row, 'other',
                                                      check_prc=True)
                        self.create_attribute(dataset, attr_name,
                                              ignore_duplicate=True)
                        self.store_stav(scrape_id, geounit_id, valid_time,
                                        attr_name, row['other_value'], row_no,
                                        'other')

                    except ValueError:
                        # treat 'other' as modifier for other columns
                        for attr in simple_attrs:
                            if row[attr]:

                                attr_name = self.mk_attr_name(row, 'other',
                                                              'other_value',
                                                              '='+attr,
                                                              check_prc=True)
                                self.create_attribute(dataset, attr_name,
                                                      ignore_duplicate=True)
                                self.store_stav(scrape_id, geounit_id,
                                                valid_time, attr_name,
                                                row[attr], row_no, attr)

                elif row['other']:
                    logger.warning(f"None-empty 'other' while 'other_value' "
                                   f"is empty in {fname}:{row_no}")
                else:
                    # the bulk of the values comes from here
                    for attr in simple_attrs:
                        if row[attr]:

                            attr_name = self.mk_attr_name(row, '='+attr,
                                                          check_prc=True)
                            self.create_attribute(dataset, attr_name,
                                                  ignore_duplicate=True)
                            self.store_stav(scrape_id, geounit_id, valid_time,
                                            attr_name, row[attr], row_no, attr)

            simpl_vals_prev = simpl_vals
            id_vals_prev = id_vals
            # group_type_prev = group_type
            row_prev = row

        _ts = datetime.datetime.now().isoformat()
        logger.info("Parsing of {fname} completed at {_ts}")
