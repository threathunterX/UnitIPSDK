#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2019/8/20 下午8:25
# @Author  : yu
# @Software: PyCharm
# @license : Copyright(C),威胁猎人
import requests
import json
import os
import subprocess
import traceback
import base64
import time

import pymysql
from DBUtils.PooledDB import PooledDB

import logging
import logging.handlers
from logging import getLogger, INFO, WARN, DEBUG, ERROR, FATAL, WARNING, CRITICAL

from pymongo import MongoClient
from Crypto.Cipher import AES
from Crypto import Random
from datetime import datetime, timedelta

from config import G_CONFIG

__all__ = ["DownLoad", "InitialPackage", "produce", "consume", "update"]
PERIMETER_VERSION = 0
BUSINESS_VERSION = 1


class ThLog(object):
    LOG_LEVEL = logging.INFO
    DATE_FORMAT = time.strftime('%Y-%m-%d', time.localtime(time.time()))

    FORMAT = '[%(asctime)s]-%(levelname)-8s<%(name)s> {%(filename)s:%(lineno)s} -> %(message)s'
    formatter = logging.Formatter(FORMAT)

    def __init__(self, module_name):
        self._normal = None
        self._error = None
        self.name = module_name

    def get_normal_log(self):
        file_name = './{0}.log'.format(self.name)
        normal_handler = logging.handlers.TimedRotatingFileHandler(filename=file_name, backupCount=30, when="D")
        normal_handler.setFormatter(self.formatter)
        normal_log = getLogger(self.name)
        normal_log.setLevel(self.LOG_LEVEL)
        normal_log.addHandler(normal_handler)
        return normal_log

    def get_error_log(self):
        file_name = './ERROR_{0}.log'.format(self.name)
        error_handler = logging.handlers.TimedRotatingFileHandler(filename=file_name, backupCount=7, when="D")
        error_handler.setFormatter(self.formatter)
        error_log = getLogger(self.name + '_error')
        error_log.setLevel(self.LOG_LEVEL)
        error_log.addHandler(error_handler)
        return error_log

    @property
    def normal_log(self):
        if not self._normal:
            self._normal = self.get_normal_log()
        return self._normal

    @property
    def error_log(self):
        if not self._error:
            self._error = self.get_error_log()
        return self._error

    def set_name(self, name):
        self.name = name

    def setLevel(self, level):
        self.normal_log.setLevel(level)

    def _backup_print(self, msg, *args, **kwargs):
        if args:
            msg = "{0}/{1}".format(msg, str(args))
        if kwargs:
            msg = "{0}/{1}".format(msg, str(kwargs))
        print(msg)

    def debug(self, msg, *args, **kwargs):
        if self.normal_log.isEnabledFor(DEBUG):
            self.normal_log._log(DEBUG, msg, args, **kwargs)
            self._backup_print(msg, args, kwargs)

    def info(self, msg, *args, **kwargs):
        if self.normal_log.isEnabledFor(INFO):
            self.normal_log._log(INFO, msg, args, **kwargs)
            self._backup_print(msg, args, kwargs)

    def warning(self, msg, *args, **kwargs):
        if self.normal_log.isEnabledFor(WARN):
            self.normal_log._log(WARNING, msg, args, **kwargs)

    def warn(self, msg, *args, **kwargs):
        if self.normal_log.isEnabledFor(WARN):
            self.normal_log._log(WARN, msg, args, **kwargs)

    def error(self, msg, *args, **kwargs):
        if self.error_log.isEnabledFor(ERROR):
            self.normal_log._log(ERROR, msg, args, **kwargs)
            self.error_log._log(ERROR, msg, args, **kwargs)

    def critical(self, msg, *args, **kwargs):
        if self.error_log.isEnabledFor(CRITICAL):
            self.normal_log._log(CRITICAL, msg, args, **kwargs)
            self.error_log._log(CRITICAL, msg, args, **kwargs)

    def fatal(self, msg, *args, **kwargs):
        if self.error_log.isEnabledFor(FATAL):
            self.normal_log._log(FATAL, msg, args, **kwargs)
            self.error_log._log(FATAL, msg, args, **kwargs)


logger = ThLog("cli")


def status_upload(version, tag):
    url = "http://{}/call_back".format(G_CONFIG.host)

    payload = {"snuser": G_CONFIG.user["snuser"], "snkey": G_CONFIG.user["snkey"], "version": version, "tag": tag}
    headers = {
        'Content-Type': "application/json"
    }

    try:
        requests.request("POST", url, data=json.dumps(payload), headers=headers, timeout=1)
        return 0
    except:
        return 1


class InitialPackage(object):
    """
    process InitialPackage
    """

    @classmethod
    def aes_decrypt_seg(cls, phoneno, snkey=G_CONFIG.user["snkey"]):
        data = base64.decodebytes(bytes(phoneno, encoding="utf8"))
        cihpertxt = data[AES.block_size:]
        remainder = len(cihpertxt) % AES.block_size
        if remainder:
            padded_value = cihpertxt + b'\0' * (AES.block_size - remainder)
        else:
            padded_value = cihpertxt
        cryptor = AES.new(bytes(snkey, encoding="utf8"), AES.MODE_CFB, data[0:AES.block_size], segment_size=128)
        plain_text = cryptor.decrypt(padded_value)
        return str(plain_text[0:len(cihpertxt)], encoding="utf8")

    @classmethod
    def download_initial(cls, url, file_name):
        """
        从oss下载数据重命名后保存
        :param url: oss下载链接
        :param file_name: 文件名
        :return: bool
        """
        try:

            file_path = "./download/" + file_name
            down_cmd = "wget '{0}' -O {1}".format(url, file_path)
            subprocess.call(down_cmd, shell=True)
            status_upload(file_name.split(".")[0], "download")
            return True
        except:
            logger.error(traceback.format_exc())
            return False

    def get_perimeter_initial(self):
        url = "https://{host}/api/v1/initial/".format(host=G_CONFIG.host)
        payload = {
            "snuser": G_CONFIG.user["snuser"]
        }
        logger.info(payload)
        try:
            r = requests.post(url, data=json.dumps(payload))
            rjson = json.loads(r.text)
            if rjson["status"] == 200:
                result = json.loads(self.aes_decrypt_seg(rjson["data"]))
                filename = result["version"] + ".txt.gz"
                if self.download_initial(url=result["link"], file_name=filename):
                    status_upload(result["version"], "download")
                    return result["version"], filename
            else:
                logger.warn("error code is {}".format(rjson["status"]))
                return ""
        except:
            logger.error(traceback.format_exc())
            return ""

    def get_business_initial(self):
        url = "https://{host}/api/v6/initial/".format(host=G_CONFIG.host)
        payload = {
            "snuser": G_CONFIG.user["snuser"]
        }
        logger.info(payload)
        try:
            r = requests.post(url, data=json.dumps(payload))
            rjson = json.loads(r.text)
            if rjson["status"] == 200:
                result = json.loads(self.aes_decrypt_seg(rjson["data"]))
                if self.download_initial(url=result["file"]["link"], file_name=result["file"]["name"]):
                    status_upload(result["file"]["name"].split(".")[0], "download")
                    return result["file"]["name"]
            else:
                logger.warn("error code is {}".format(rjson["status"]))
                return ""
        except:
            logger.error(traceback.format_exc())
            return ""

    @classmethod
    def unzip_business(cls, filename):
        file_new = filename.split('.')[0]
        cmd = "gunzip ./download/{file_old} && mv ./download/{file_new} ./task/ ".format(file_old=filename,
                                                                                         file_new=file_new)
        subprocess.call(cmd, shell=True)
        return file_new

    @classmethod
    def unzip_perimeter(cls, filename):
        file_new = filename[:-3]
        cmd = "gunzip ./download/{file_old} && mv ./download/{file_new} ./task/ ".format(file_old=filename,
                                                                                         file_new=file_new)
        subprocess.call(cmd, shell=True)
        return file_new

    @classmethod
    def write_data(cls, database, filename, version):
        def parse_data(origin_data):
            """
            解析成 json 数据入mongo
            :param origin_data: 文件里的每一行的数据
            :return:
            """
            try:
                data_list = origin_data.split("\n")[0].split("\t")
                if version == BUSINESS_VERSION:
                    return {"ip": data_list[0],
                            "type": data_list[1],
                            "b_risk_tag": data_list[2],
                            "b_risk_score": data_list[3],
                            "b_level": data_list[4],
                            "country": data_list[5],
                            "province": data_list[6],
                            "city": data_list[7],
                            "district": data_list[8],
                            "owner": data_list[9],
                            "latitude": data_list[10],
                            "longitude": data_list[11],
                            "adcode": data_list[12],
                            "areacode": data_list[13],
                            "continent": data_list[14],
                            }
                if version == PERIMETER_VERSION:
                    return {"ip": data_list[0],
                            "type": data_list[1],
                            "p_risk_tag": data_list[2],
                            "p_risk_score": data_list[3],
                            "p_level": data_list[4],
                            "country": data_list[5],
                            "province": data_list[6],
                            "city": data_list[7],
                            "district": data_list[8],
                            "owner": data_list[9],
                            "latitude": data_list[10],
                            "longitude": data_list[11],
                            "adcode": data_list[12],
                            "areacode": data_list[13],
                            "continent": data_list[14],
                            }
            except:
                logger.error(traceback.format_exc())
                return {}

        def cut_file(fp, size):
            count = 1
            data = []
            for line in fp:
                if count % size == 0:
                    yield data
                    data = []
                data.append(line)
                count = count + 1
            if data:
                yield

        try:
            with open("./task/{}".format(filename), "r") as f:
                for lines in cut_file(f, 100000):
                    json_data_list = list(map(parse_data, lines))
                    if database == "mongodb":
                        # start_time = time.time()
                        n = 0
                        while n < 5:
                            success = False
                            if version == PERIMETER_VERSION:
                                success = IpToMongoDB.get_instance().batch_insert(json_data_list)
                            if version == BUSINESS_VERSION:
                                success = IpToMongoDB.get_instance().update(json_data_list, version)
                            if success:
                                status_upload(filename, "db")
                                break
                            else:
                                n = n + 1
                                if n == 5:
                                    logger.error("{}入库尝试5次未成功".format(filename))
                                    status_upload(filename, "db_fail")

                        # logger.info("入库 耗时:{0}, 共插入数据{1}".format(time.time() - start_time, len(json_data_list)))
                    if database == "mysql":
                        n = 0
                        while n < 5:
                            success = False
                            if version == PERIMETER_VERSION:
                                success = IpToMysql.get_instance().execute_many_sql_with_commit(json_data_list)
                            if version == BUSINESS_VERSION:
                                success = IpToMysql.get_instance().execute_update_sql_with_commit(json_data_list,
                                                                                                  version)
                            if success:
                                status_upload(filename, "db")
                                break
                            else:
                                n = n + 1
                                if n == 5:
                                    logger.error("{}入库尝试5次未成功".format(filename))
                                    status_upload(filename, "db_fail")

        except:
            logger.error("报错文件:{0}/n, {1}".format(filename, traceback.format_exc()))
        finally:
            cmd = "rm -rf ./task/{}".format(filename)
            subprocess.call(cmd, shell=True)
            return

    def process(self, database):
        path_to_task = "./task/"
        if not os.path.isdir(path_to_task):
            os.mkdir(path_to_task)
        path_to_watch = "./download/"
        if not os.path.isdir(path_to_watch):
            os.mkdir(path_to_watch)
        if database == "mysql":
            IpToMysql.get_instance().create_table()
        # 下载解析边界安全版全量包
        curver, filename = self.get_perimeter_initial()
        file_new = self.unzip_perimeter(filename)
        self.write_data(database, file_new, PERIMETER_VERSION)
        while True:
            nextver = update(database, curver)
            if nextver:
                curver = nextver
            else:
                break
        # 下载解析业务安全版全量包
        filename = self.get_business_initial()
        file_new = self.unzip_business(filename)
        self.write_data(database, file_new, BUSINESS_VERSION)


class DownLoad(object):
    """
    download handle
    """

    @classmethod
    def aes_encrypt_seg(cls, phoneno, snkey=G_CONFIG.user["snkey"]):
        remainder = len(phoneno) % AES.block_size
        if remainder:
            padded_value = phoneno + '\0' * (AES.block_size - remainder)
        else:
            padded_value = phoneno
        # a random 16 byte key
        iv = Random.new().read(AES.block_size)
        # CFB mode
        cipher = AES.new(bytes(snkey, encoding='utf8'), AES.MODE_CFB, iv, segment_size=128)
        # drop the padded value(phone number length is short the 16bytes)
        value = cipher.encrypt(bytes(padded_value, encoding="utf8")[:len(phoneno)])
        ciphertext = iv + value
        return str(base64.encodebytes(ciphertext).strip(), encoding="utf8")

    @classmethod
    def aes_decrypt_seg(cls, phoneno, snkey=G_CONFIG.user["snkey"]):
        data = base64.decodebytes(bytes(phoneno, encoding="utf8"))
        cihpertxt = data[AES.block_size:]
        remainder = len(cihpertxt) % AES.block_size
        if remainder:
            padded_value = cihpertxt + b'\0' * (AES.block_size - remainder)
        else:
            padded_value = cihpertxt
        cryptor = AES.new(bytes(snkey, encoding="utf8"), AES.MODE_CFB, data[0:AES.block_size], segment_size=128)
        plain_text = cryptor.decrypt(padded_value)
        return str(plain_text[0:len(cihpertxt)], encoding="utf8")

    @classmethod
    def download(cls, url, file_name):
        """
        从oss下载数据重命名后保存
        :param url: oss下载链接
        :param file_name: 文件名
        :return: bool
        """
        try:
            r = requests.get(url)
            file_path = "./download/" + file_name
            with open(file_path, "wb") as code:
                code.write(r.content)
            cmd = "gunzip {file}".format(file=file_path)
            subprocess.call(cmd, shell=True)
            status_upload(file_name.split(".")[0], "download")
            return True
        except:
            logger.error(traceback.format_exc())
            return False

    @classmethod
    def download_perimeter(cls, url, file_name):
        """
        从oss下载数据重命名后保存
        :param url: oss下载链接
        :param file_name: 文件名
        :return: bool
        """
        try:
            file_path = "./download/" + file_name
            down_cmd = "wget '{0}' -O {1}".format(url, file_path)
            subprocess.call(down_cmd, shell=True)
            status_upload(file_name.split(".")[0], "download")
            return True
        except:
            logger.error(traceback.format_exc())
            return False

    def get_upgrade_resp(self, data, version=BUSINESS_VERSION):
        """
        获取更新包下载链接信息
        :param data:
        :param version:
        :return: dict()
        """
        url = "https://{host}/api/v6/upgrade/".format(host=G_CONFIG.host)
        if version == PERIMETER_VERSION:
            url = "https://{host}/api/v1/upgrade/".format(host=G_CONFIG.host)

        pstr = json.dumps(data)

        cstr = self.aes_encrypt_seg(pstr)

        payload = {
            "snuser": G_CONFIG.user["snuser"],
            "data": cstr
        }

        try:
            r = requests.post(url, data=json.dumps(payload))
            rjson = json.loads(r.text)
            if rjson["status"] == 200:
                return json.loads(self.aes_decrypt_seg(rjson["data"]))
            else:
                logger.warn("error code is {}".format(rjson["status"]))
                return {}
        except:
            logger.error(traceback.format_exc())
            return {}

    def run(self):
        """
        持续从服务端下载文件到本地
        :return:
        """
        # 先下载全量包
        # self.get_initial_resp()
        curver = G_CONFIG.curver
        while True:
            result = self.get_upgrade_resp({"curver": curver, "limit": 100})
            count = result.get("count", 0)
            curver = result.get("nextver", curver)
            files = result.get("files", [])
            if count:
                for file in files:
                    n = 0
                    while n < 10:
                        if self.download(url=file["link"], file_name=file["name"]):
                            status_upload(file["name"].split(".")[0], "download")
                            break
                        else:
                            n = n + 1
                            if n == 10:
                                logger.error("尝试10次未下载成功")
                                status_upload(file["name"].split(".")[0], "download_fail")

            time.sleep(10)


class IpToMongoDB(object):
    """
    数据设计结构:{"ip": str,  IP
                "type": ,IP类型，包括家庭宽带、数据中心、移动网络、企业专线、校园单位、未知
                "b_risk_tag": 业务安全风险标签
                "b_risk_score": 业务安全风险分数，范围0-100，分数越高被黑产持有的概率也就越高
                "b_level":业务安全风险等级，包括高、中、低、无
                "p_risk_tag": 边界安全风险标签
                "p_risk_score": 业务安全风险分数，范围0-100，分数越高被黑产持有的概率也就越高
                "p_level":业务安全风险等级，包括高、中、低、无
                "country": 国家
                "province": 省份
                "city": 城市
                "district": 区县
                 "owner": 运营商
                 "latitude": 纬度
                 "longitude": 经度
                 "adcode": 行政区划代码
                 "areacode": 国家编码
                 "continent": 大洲
                }
    """
    _instance = None

    @classmethod
    def get_instance(cls):
        if not cls._instance:
            cls._instance = IpToMongoDB()
        return cls._instance

    def __init__(self):
        self.conn = MongoClient(G_CONFIG.mongodb["uri"])
        self.conn.get_database(G_CONFIG.mongodb["db"]).get_collection(G_CONFIG.mongodb["collection"]). \
            create_index([("ip", 1)], unique=True)

    def get_conn(self):
        """
        返回collection的连接
        :return:
        """
        db_name = G_CONFIG.mongodb["db"]
        coll_name = G_CONFIG.mongodb["collection"]

        return self.conn[db_name][coll_name]

    def batch_insert(self, data_list):
        """
        批量插入信息
        :param data_list: [{"ip": str,  IP
                "type": ,IP类型，包括家庭宽带、数据中心、移动网络、企业专线、校园单位、未知
                "b_risk_tag": 业务安全风险标签
                "b_risk_score": 业务安全风险分数，范围0-100，分数越高被黑产持有的概率也就越高
                "b_level":业务安全风险等级，包括高、中、低、无
                "p_risk_tag": 边界安全风险标签
                "p_risk_score": 业务安全风险分数，范围0-100，分数越高被黑产持有的概率也就越高
                "p_level":业务安全风险等级，包括高、中、低、无
                "country": 国家
                "province": 省份
                "city": 城市
                "district": 区县
                 "owner": 运营商
                 "latitude": 纬度
                 "longitude": 经度
                 "adcode": 行政区划代码
                 "areacode": 国家编码
                 "continent": 大洲
                }...]
        :return: int(1: success, 0: failed)
        """
        if not data_list:
            return 0

        try:
            self.get_conn().insert_many(data_list, ordered=False, bypass_document_validation=True)
            return 1
        except:
            logger.error(traceback.format_exc())
            return 0

    def update(self, data_list, version):
        """
        批量操作,存在则更新,不存在则insert
        :param data_list:
        :param version:
        :return:
        """
        if not data_list:
            return 0
        try:
            for data in data_list:
                result = self.get_conn().find_one({"ip": data["ip"]})
                if result:
                    if version == PERIMETER_VERSION:
                        self.get_conn().update_one({"ip": data["ip"]}, {'$set': {
                            "p_risk_tag": data["p_risk_tag"],
                            "p_risk_score": data["p_risk_score"],
                            "p_level": data["p_level"]
                        }})
                    if version == BUSINESS_VERSION:
                        new_tag = data["b_risk_tag"][:2]
                        index = result["b_risk_tag"].find(new_tag)
                        if index == -1:
                            if data["type"] == "数据中心":
                                result["b_risk_tag"] = result["b_risk_tag"].replace("机房流量", "")
                            data["b_risk_tag"] = result["b_risk_tag"] + "|" + data["b_risk_tag"]
                        else:
                            data["b_risk_tag"] = result["b_risk_tag"].replace(
                                result["b_risk_tag"][index + 3:index + 22],
                                data["b_risk_tag"][3:22])
                        self.get_conn().update_one({"ip": data["ip"]}, {'$set': {
                            "b_risk_tag": data["b_risk_tag"],
                            "b_risk_score": data["b_risk_score"],
                            "b_level": data["b_level"]
                        }})
                else:
                    self.get_conn().insert(data)
            return 1
        except:
            logger.error(traceback.format_exc())
            return 0


class IpToMysql(object):
    _instance = None

    @classmethod
    def get_instance(cls):
        if not cls._instance:
            cls._instance = IpToMysql(**G_CONFIG.mysql)
        return cls._instance

    def __init__(self, host, port, user, password, db, table, charset='utf8', **kwargs):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.db = db
        self.charset = charset
        self.table = table

        self.pool = PooledDB(
            creator=pymysql, maxconnections=10, mincached=5, blocking=True,
            host=self.host, port=self.port, user=self.user, passwd=self.password, database=self.db,
            charset=self.charset, **kwargs
        )

    def create_table(self):
        conn = self.pool.connection()
        cursor = conn.cursor()
        sql = "create table if not exists `{table}` " \
              "(`ip` varchar(20) NOT NULL ," \
              "`type` varchar(10) COMMENT '类型', " \
              "`b_risk_tag` varchar(200) DEFAULT '' COMMENT '业务安全风险标签'," \
              "`b_risk_score` varchar(10) DEFAULT '' COMMENT '业务安全风险分数'," \
              "`b_level` varchar(10) DEFAULT '' COMMENT '业务安全风险等级'," \
              "`p_risk_tag` varchar(2000) DEFAULT '' COMMENT '边界安全风险标签'," \
              "`p_risk_score` varchar(10) DEFAULT '' COMMENT '边界安全风险分数'," \
              "`p_level` varchar(10) DEFAULT '' COMMENT '边界安全风险等级'," \
              "`country` varchar(50) COMMENT '国家', " \
              "`province` varchar(100) COMMENT '省份'," \
              "`city` varchar(100) COMMENT '城市'," \
              "`district` varchar(100) COMMENT '区县'," \
              "`owner` varchar(200) COMMENT '运营商'," \
              "`latitude` varchar(30) COMMENT '维度'," \
              "`longitude` varchar(30) COMMENT '经度'," \
              "`adcode` varchar(30) COMMENT '行政区划代码'," \
              "`areacode` varchar(30) COMMENT '国家编码'," \
              "`continent` varchar(30) COMMENT '大洲'," \
              " primary key (ip)) DEFAULT CHARSET=utf8;".format(table=self.table)
        cursor.execute(sql)
        conn.commit()
        cursor.close()
        conn.close()
        return 1

    def execute_many_sql_with_commit(self, param_list):
        """
        执行更新或插入语句，批量插入
        :param param_list: [(), (), ...]
        :return:
        """
        if not param_list:
            return 0
        try:
            conn = self.pool.connection()
            cursor = conn.cursor()
            sql = "INSERT INTO `{table}` " \
                  "(`ip`, `type`, `p_risk_tag`, `p_risk_score`, `p_level`,`country`, `province`, `city`, `district`, " \
                  "`owner`,`latitude`,`longitude`,`adcode`,`areacode`,`continent`) " \
                  "VALUES(%(ip)s, %(type)s, %(p_risk_tag)s, %(p_risk_score)s, %(p_level)s,%(country)s, %(province)s, " \
                  "%(city)s,%(district)s, %(owner)s, %(latitude)s,%(longitude)s,%(adcode)s," \
                  "%(areacode)s,%(continent)s) ON DUPLICATE KEY UPDATE p_risk_score=VALUES(p_risk_score)," \
                  "p_risk_tag=VALUES(p_risk_tag),p_level=VALUES(p_level)"
            sql = sql.format(table=self.table)
            cursor.executemany(sql, param_list)
            conn.commit()
            cursor.close()
            conn.close()
            return 1
        except:
            logger.error(traceback.format_exc())
            return 0

    def execute_update_sql_with_commit(self, param_list, version):
        """
        执行更新或插入语句,单条插入
        :param param_list: [(), (), ...]
        :param version:
        :return:
        """
        if not param_list:
            return 0
        try:
            conn = self.pool.connection()
            with conn.cursor() as cursor:
                for data in param_list:
                    query_sql = "SELECT `b_risk_tag` from `{table}` where ip=%(ip)s"
                    query_sql = query_sql.format(table=self.table)
                    rows = cursor.execute(query_sql, data)
                    if rows == 0:
                        if version == PERIMETER_VERSION:
                            insert_sql = "INSERT INTO `{table}` " \
                                         "(`ip`, `type`, `p_risk_tag`, `p_risk_score`, `p_level`,`country`, `province`, `city`, " \
                                         "`district`, `owner`,`latitude`,`longitude`,`adcode`,`areacode`,`continent`) " \
                                         "VALUES(%(ip)s, %(type)s, %(p_risk_tag)s, %(p_risk_score)s, %(p_level)s,%(country)s, " \
                                         "%(province)s, %(city)s,%(district)s, %(owner)s, %(latitude)s,%(longitude)s,%(adcode)s," \
                                         "%(areacode)s,%(continent)s)"
                            insert_sql = insert_sql.format(table=self.table)
                            cursor.execute(insert_sql, data)
                            conn.commit()
                        if version == BUSINESS_VERSION:
                            insert_sql = "INSERT INTO `{table}` " \
                                         "(`ip`, `type`, `b_risk_tag`, `b_risk_score`, `b_level`,`country`, `province`, `city`, " \
                                         "`district`, `owner`,`latitude`,`longitude`,`adcode`,`areacode`,`continent`) " \
                                         "VALUES(%(ip)s, %(type)s, %(b_risk_tag)s, %(b_risk_score)s, %(b_level)s,%(country)s, " \
                                         "%(province)s, %(city)s,%(district)s, %(owner)s, %(latitude)s,%(longitude)s,%(adcode)s," \
                                         "%(areacode)s,%(continent)s)"
                            insert_sql = insert_sql.format(table=self.table)
                            cursor.execute(insert_sql, data)
                            conn.commit()
                    else:
                        if version == PERIMETER_VERSION:
                            update_sql = "UPDATE `{table}` set `p_risk_tag` =%(p_risk_tag)s,`p_risk_score` =%(p_risk_score)s," \
                                         "`p_level`=%(p_level)s where ip=%(ip)s"
                            update_sql = update_sql.format(table=self.table)
                            cursor.execute(update_sql, data)
                            conn.commit()
                        if version == BUSINESS_VERSION:
                            result = cursor.fetchone()
                            result = list(result)
                            new_tag = data["b_risk_tag"][:2]
                            index = result[0].find(new_tag)
                            # 风险标签是否存在，存在则更新时间，不存在则追加
                            if index == -1:
                                if data["type"] == "数据中心":
                                    result[0] = result[0].replace("机房流量", "")
                                if result[0] == "":
                                    data["b_risk_tag"] = data["b_risk_tag"]
                                else:
                                    data["b_risk_tag"] = result[0] + "|" + data["b_risk_tag"]

                            else:
                                data["b_risk_tag"] = result[0].replace(result[0][index + 3:index + 22],
                                                                       data["b_risk_tag"][3:22])
                            update_sql = "UPDATE `{table}` set `b_risk_tag` =%(b_risk_tag)s,`b_risk_score` =%(b_risk_score)s," \
                                         "`b_level`=%(b_level)s where ip=%(ip)s"
                            update_sql = update_sql.format(table=self.table)
                            cursor.execute(update_sql, data)
                            conn.commit()

            conn.close()
            return 1
        except:
            logger.error(traceback.format_exc())
            return 0


def produce():
    path_to_task = "./task/"
    if not os.path.isdir(path_to_task):
        os.mkdir(path_to_task)
    path_to_watch = "./download/"
    if not os.path.isdir(path_to_watch):
        os.mkdir(path_to_watch)
    before_list = []
    while True:
        after_list = os.listdir(path_to_watch)
        if not after_list:
            time.sleep(10)
            continue
        added = [f for f in after_list if f not in before_list]
        # logger.info("本轮新增文件：{}".format(added))
        if added:
            for f in added:
                try:
                    if ".gz" in f:
                        subprocess.call("gunzip ./download/{file_old} && mv ./download/{file_new} ./task/ ".
                                        format(file_old=f, file_new=f.split('.')[0]),
                                        shell=True)
                    elif not f.isdigit():
                        continue
                    else:
                        subprocess.call("mv ./download/{file} ./task/".format(file=f), shell=True)
                except:
                    logger.error(traceback.format_exc())
                    continue
        before_list = after_list
        time.sleep(10)


def consume(database):
    def parse_data(origin_data):
        """
        解析成 json 数据入mongo
        :param origin_data: 文件里的每一行的数据
        :return:
        """
        try:
            data_list = origin_data.split("\n")[0].split("\t")
            return {"ip": data_list[0],
                    "type": data_list[1],
                    "b_risk_tag": data_list[2],
                    "b_risk_score": data_list[3],
                    "b_level": data_list[4],
                    "country": data_list[5],
                    "province": data_list[6],
                    "city": data_list[7],
                    "district": data_list[8],
                    "owner": data_list[9],
                    "latitude": data_list[10],
                    "longitude": data_list[11],
                    "adcode": data_list[12],
                    "areacode": data_list[13],
                    "continent": data_list[14],
                    }
        except:
            logger.error(traceback.format_exc())
            return {}

    def run(file):
        try:
            with open("./task/{}".format(file), "r") as fp:
                lines = fp.readlines()
                json_data_list = list(map(parse_data, lines))

                if database == "mongodb":
                    # start_time = time.time()
                    n = 0
                    while n < 5:
                        if IpToMongoDB.get_instance().update(json_data_list, version=BUSINESS_VERSION):
                            status_upload(file, "db")
                            break
                        else:
                            n = n + 1
                            if n == 5:
                                logger.error("{}入库尝试5次未成功".format(file))
                                status_upload(file, "db_fail")

                    # logger.info("入库 耗时:{0}, 共插入数据{1}".format(time.time() - start_time, len(json_data_list)))
                if database == "mysql":
                    # start_time = time.time()
                    n = 0
                    while n < 5:
                        if IpToMysql.get_instance().execute_update_sql_with_commit(json_data_list,
                                                                                   version=BUSINESS_VERSION):
                            status_upload(file, "db")
                            break
                        else:
                            n = n + 1
                            if n == 5:
                                logger.error("{}入库尝试5次未成功".format(file))
                                status_upload(file, "db_fail")
        except:
            logger.error("报错文件:{0}/n, {1}".format(f, traceback.format_exc()))
        finally:
            cmd = "rm -rf ./task/{}".format(file)
            subprocess.call(cmd, shell=True)
            return

    path_to_task = "./task/"
    if not os.path.isdir(path_to_task):
        os.mkdir(path_to_task)
    while True:
        files = os.listdir(path_to_task)
        files.sort()
        if files:
            for f in files:
                if f.endswith(".txt"):
                    continue
                run(f)
        else:
            time.sleep(10)


def update(database, curver):
    def get_download_link():
        filename = curver + ".txt.gz"
        download_obj = DownLoad()
        result = download_obj.get_upgrade_resp({"curver": curver, "type": 0}, version=PERIMETER_VERSION)
        link = result.get("link", "")
        if link:
            n = 0
            while n < 10:
                if download_obj.download_perimeter(url=link, file_name=filename):
                    status_upload(curver, "download")
                    break
                else:
                    n = n + 1
                    if n == 10:
                        logger.error("尝试10次未下载成功")
                        status_upload(curver, "download_fail")
        return result.get("nextver", ""), filename

    def unzip(filename):
        file_new = filename[:-3]
        cmd = "gunzip ./download/{file_old} && mv ./download/{file_new} ./task/ ".format(file_old=filename,
                                                                                         file_new=file_new)
        subprocess.call(cmd, shell=True)
        return file_new

    def parse_data(origin_data):
        """
        解析成 json 数据入mongo
        :param origin_data: 文件里的每一行的数据
        :return:
        """
        try:
            data_list = origin_data.split("\n")[0].split("\t")
            return {"ip": data_list[0],
                    "type": data_list[1],
                    "p_risk_tag": data_list[2],
                    "p_risk_score": data_list[3],
                    "p_level": data_list[4],
                    "country": data_list[5],
                    "province": data_list[6],
                    "city": data_list[7],
                    "district": data_list[8],
                    "owner": data_list[9],
                    "latitude": data_list[10],
                    "longitude": data_list[11],
                    "adcode": data_list[12],
                    "areacode": data_list[13],
                    "continent": data_list[14],
                    }
        except:
            logger.error(traceback.format_exc())
            return {}

    def cut_file(fp, size):
        count = 1
        data = []
        for line in fp:
            if count % size == 0:
                yield data
                data = []
            data.append(line)
            count = count + 1
        if data:
            yield

    def write_data(filename):
        try:
            with open("./task/{}".format(filename), "r") as f:
                for lines in cut_file(f, 100000):
                    json_data_list = list(map(parse_data, lines))
                    if database == "mongodb":
                        # start_time = time.time()
                        n = 0
                        while n < 5:
                            if IpToMongoDB.get_instance().update(json_data_list, version=PERIMETER_VERSION):
                                status_upload(filename, "db")
                                break
                            else:
                                n = n + 1
                                if n == 5:
                                    logger.error("{}入库尝试5次未成功".format(filename))
                                    status_upload(filename, "db_fail")

                        # logger.info("入库 耗时:{0}, 共插入数据{1}".format(time.time() - start_time, len(json_data_list)))
                    if database == "mysql":
                        # start_time = time.time()
                        n = 0
                        while n < 5:
                            if IpToMysql.get_instance().execute_update_sql_with_commit(json_data_list, version=PERIMETER_VERSION):
                                status_upload(filename, "db")
                                break
                            else:
                                n = n + 1
                                if n == 5:
                                    logger.error("{}入库尝试5次未成功".format(filename))
                                    status_upload(filename, "db_fail")

                    # logger.info("入库 耗时:{0}, 共插入数据{1}".format(time.time() - start_time, len(json_data_list)))
        except:
            logger.error("报错文件:{0}/n, {1}".format(filename, traceback.format_exc()))
        finally:
            cmd = "rm -rf ./task/{}".format(filename)
            subprocess.call(cmd, shell=True)
            return

    if curver == "schedule":
        curver = (datetime.now() - timedelta(days=0)).strftime("%Y%m%d")
    nextver, file_name = get_download_link()
    task_file = unzip(file_name)
    write_data(task_file)
    logger.info("update success")
    return nextver
