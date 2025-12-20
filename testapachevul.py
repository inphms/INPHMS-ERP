#!/usr/bin/env python
#coding:utf-8
#Author:se55i0n
#针对常见sql、No-sql数据库进行安全检查
import sys
import IPy
import ipaddress
import time
import socket
import gevent
import argparse
from gevent import monkey
from multiprocessing.dummy import Pool as ThreadPool


monkey.patch_all()

class DBScanner(object):
	def __init__(self, target, thread):
		self.target = target
		self.thread = thread
		self.ips    = []
		self.ports  = []
		self.time   = time.time()
		self.get_ip()
		self.get_port()
		self.check = check()
	
	def get_ip(self):
		#获取待扫描地址段
		for ip in IPy.IP(self.target):
			self.ips.append(str(ip))

	def get_port(self):
		self.ports = list(p for p in service.itervalues())

	def scan(self, ip, port):
		try:
			s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
			s.settimeout(0.2)
			if s.connect_ex((ip, port)) == 0:
				self.handle(ip, port)
		except Exception as e:
			pass
		finally:
			s.close()

	def handle(self, ip, port):
		for v,k in service.iteritems():
			if k == str(port):
				if v == 'mysql':
					self.check.mysql(ip)
				elif v == 'mssql':
					self.check.mssql(ip)
				elif v == 'oracle':
					self.check.oracle(ip)
				elif v == 'postgresql':
					self.check.postgresql(ip)
				elif v == 'redis':
					self.check.redis(ip)
				elif v == 'mongodb':
					self.check.mongodb(ip)
				elif v == 'memcached':
					self.check.memcached(ip)
				else:
					self.check.elasticsearch(ip)

	def start(self, ip):
		try:
			gevents = []
			for port in self.ports:
				gevents.append(gevent.spawn(self.scan, ip, int(port)))
			gevent.joinall(gevents)
		except Exception as e:
			pass

	def run(self):
		try:
			pool = ThreadPool(processes=self.thread)
			pool.map_async(self.start, self.ips).get(0xffff)
			pool.close()
			pool.join()
		except Exception as e:
			pass
		except KeyboardInterrupt:
			print(u'\n{}[-] 用户终止扫描...{}'.format(R, W))
			sys.exit(1)
		finally:
			print('-'*55)
			print(u'{}[+] 扫描完成耗时 {} 秒.{}'.format(O, time.time()-self.time, W)) 
def banner():
	banner = '''
    ____  ____ _____
   / __ \/ __ ) ___/_________ _____  ____  ___  _____
  / / / / __  \__ \/ ___/ __ `/ __ \/ __ \/ _ \/ ___/
 / /_/ / /_/ /__/ / /__/ /_/ / / / / / / /  __/ /
/_____/_____/____/\___/\__,_/_/ /_/_/ /_/\___/_/
    '''
	print(B + banner + W)
	print('-'*55)

B = '\033[1;34m'
W = '\033[0m'
G = '\033[1;32m'
O = '\033[1;33m'
R = '\033[1;31m'

def main():
	banner()
	parser = argparse.ArgumentParser(description='Example: python {} 192.168.1.0/24'.format(sys.argv[0]))
	parser.add_argument('target', help=u'192.168.1.0/24')
	parser.add_argument('-t', type=int, default=50, dest='thread', help=u'线程数(默认50)')
	args   = parser.parse_args()
	myscan = DBScanner(args.target, args.thread)
	myscan.run()

service = {'mssql':'1433',
        'oracle':'1521',
        'mysql':'3306',
        'postgresql':'5432',
        'redis':'6379',
        'elasticsearch':'9200',
        'memcached':'11211',
        'mongodb':'27017'}

# if __name__ == '__main__':
# 	ip = "192.168.1.0/24"
# 	ips = []

# 	for ip in IPy.IP(ip): 
# 		s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
# 		s.settimeout(0.2)
# 		for port in list(v for k,v in service.items()):
# 			# print("Scanning "+str(ip)+":"+str(port))
# 			if s.connect_ex((str(ip), int(port))) == 0:
# 				print(str(ip)+":"+str(port)+" is open")
passwd = ['openpgpwd','123456','admin','root','password','123123','123','1','','{user}',
		  '{user}{user}','{user}1','{user}123','{user}2016','{user}2015',
		  '{user}!','P@ssw0rd!!','qwa123','12345678','test','123qwe!@#',
		  '123456789','123321','1314520','666666','woaini','fuckyou','000000',
		  '1234567890','8888888','qwerty','1qaz2wsx','abc123','abc123456',
		  '1q2w3e4r','123qwe','159357','p@ssw0rd','p@55w0rd','password!',
		  'p@ssw0rd!','password1','r00t','system','111111','admin']
import psycopg2
if __name__ == '__main__':
	ip = "192.168.0.22"
	for pwd in passwd:
		try:
			pwd = pwd.replace('{user}', 'postgres')
			# conn = psycopg2.connect(user="postgres", password=pwd, host=ip, port="5432", connect_timeout=3)
			conn = psycopg2.connect(port=5432, user='openpg', password=pwd)
			print("postgres/postgres:"+pwd+" is valid")
			conn.close()
			break
		except Exception as e:
			print(e)
			pass