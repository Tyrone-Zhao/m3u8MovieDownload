import os
import re
import sys
import time
import getopt
import platform
import requests
from tqdm import tqdm
from pathlib import Path
from Crypto.Cipher import AES
from datetime import timedelta
from collections import OrderedDict
from multiprocessing import Pool, cpu_count
from tornado import httpclient, gen, ioloop, queues


def checkDownloadFolder(download_path, ty=".ts"):
    """ 返回下载目录中的文件list """
    temp = []
    try:
        temp += [os.path.abspath(p) for p in Path(download_path).glob(f'**/*{ty}')]
    except PermissionError:
        pass

    def sortNum(name):
        num = "0"
        for n in name:
            if n.isdigit():
                num += n
        return int(num)

    return sorted(temp, key=sortNum)


def testRequest(pd_url):
    """ 测试m3u8文件是否可以正常下载 """
    res = requests.get(pd_url)
    if b"404 Not Found" in res.content:
        return False
    return True


def getFileLine(url):
    """ 获取file_url, 即所有m3u8文件的url地址 """
    all_content = requests.get(url).text  # 获取第一层M3U8文件内容
    if "#EXTM3U" not in all_content:
        raise BaseException("非M3U8的链接")

    http = r'((http|ftp|https)://(([a-zA-Z0-9\._-]+\.[a-zA-Z]{2,6})|([0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3})))'
    url_head = re.findall(http, url)[0][0]

    if "EXT-X-STREAM-INF" in all_content:  # 第一层
        file_line = all_content.split("\n")
        for line in file_line:
            if '.m3u8' in line:
                url = url_head + line  # 拼出第二层m3u8的URL
                all_content = requests.get(url).text

    file_line = all_content.split("\n")
    begin, flag = True, 0
    res_ = OrderedDict()
    key = ""
    for index in range(len(file_line)):  # 第二层
        line = file_line[index]
        if "#EXT-X-KEY" in line:  # 找解密Key
            method_pos = line.find("METHOD")
            comma_pos = line.find(",")
            method = line[method_pos:comma_pos].split('=')[1]
            print("Decode Method：", method)

            uri_pos = line.find("URI")
            quotation_mark_pos = line.rfind('"')
            key_path = line[uri_pos:quotation_mark_pos].split('"')[1]

            key_url = url.rsplit("/", 1)[0] + "/" + key_path  # 拼出key解密密钥URL
            res = requests.get(key_url)
            key = res.content
            print("key：", key)

        if "EXTINF" in line:  # 找ts地址并下载
            if "http" in file_line[index + 1]:
                pd_url = file_line[index + 1]
            else:
                pd_url1 = url.rsplit("/", 1)[0] + "/" + file_line[index + 1]  # 拼出ts片段的URL
                pd_url2 = url_head + "/" + file_line[index + 1]  # 拼出ts片段的URL

                if begin and testRequest(pd_url1):
                    flag = 1
                    begin = False
                elif begin and testRequest(pd_url2):
                    flag = 2
                    begin = False

                pd_url = pd_url1 if flag == 1 else pd_url2

            c_fule_name = file_line[index + 1].rsplit("/", 1)[-1]
            res_[c_fule_name] = pd_url

    return key, res_


def createDownloadFolder(download_path):
    """ 创建下载目录 """
    if not os.path.exists(download_path):
        os.mkdir(download_path)

    # # 新建日期文件夹
    # download_path = os.path.join(download_path) + "/" + datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    # if not os.path.exists(download_path):
    #     os.mkdir(download_path)


def integrityCheck(download_path, file_line):
    """ 检查是否有缺失的.ts文件，如有则重新下载 """
    temp = checkDownloadFolder(download_path, ".ts")

    if temp:
        max_num = 0
        res = []
        for t in temp:
            filepath, tempfilename = os.path.split(t)
            filename, extension = os.path.splitext(tempfilename)
            num = "0"
            for f in filename:
                if f.isdigit():
                    num += f
            if int(num) > max_num:
                max_num = int(num)
            res.append(tempfilename)

        res = set(res)
        for r in res:
            if "_" in r:
                r = r.rsplit("_")[-1]
            if file_line.get(r):
                del file_line[r]

    return file_line


def processingFileLine(file_line, download_path):
    """ 把file_line变成(url, download_path, line)的元组形式list """
    res = []
    for f_name, f_url in file_line.items():
        res.append((download_path, f_name, f_url))

    return res


def theProgressBar(len_file_line, download_path):
    """ 显示进度条 """
    temp = checkDownloadFolder(download_path, ".ts")

    for i in tqdm(range(len(temp), len_file_line)):
        while True:
            temp = checkDownloadFolder(download_path, ".ts")
            if len(temp) >= i:
                break


def runMulti(thing):
    key, file, download_path = thing
    with open(os.path.join(download_path, file), 'rb') as f:
        cryptor = AES.new(key, AES.MODE_CBC, key)
        text = cryptor.decrypt(f.read())
    with open(os.path.join(download_path, file), 'wb') as f:
        f.write(text)


def decrptAES(key, file_line, download_path):
    cpu_num = cpu_count()
    p = Pool(cpu_num)
    things = [(key, file[0], download_path) for file in file_line]
    p.map(runMulti, things)
    p.close()
    p.join()


def merge_file(path):
    os.chdir(path)
    plat_f = platform.system()
    if "Win" in plat_f:
        str1 = ""
        for s in checkDownloadFolder(path):
            str1 += s + " "
        cmd = f"copy /b {str1} new.tmp"
        os.system(cmd)
        os.system('del /Q *.ts')
        os.system('del /Q *.mp4')
        os.rename("new.tmp", "new.mp4")
    elif "Dar" in plat_f:
        str1 = ""
        for s in checkDownloadFolder(path):
            str1 += s + " "
        cmd = f'cat {str1} > new.mp4'
        os.system(cmd)
        os.system('rm -f *.ts')
        os.rename("new.mp4", "new.ts")
        os.system(f'cat new.ts > new.mp4')


class AsySpider(object):
    """A simple class of asynchronous spider."""

    def __init__(self, urls, concurrency=10, results=None, **kwargs):
        urls.reverse()
        self.urls = urls
        self.concurrency = concurrency
        self._q = queues.Queue()
        self._fetching = set()
        self._fetched = set()
        if results is None:
            self.results = []

    def fetch(self, url, **kwargs):
        fetch = getattr(httpclient.AsyncHTTPClient(), 'fetch')
        return fetch(url, raise_error=False, **kwargs)

    def handle_html(self, url, html):
        """handle html page"""
        print(url)

    def handle_response(self, url, response):
        """inherit and rewrite this method if necessary"""
        if response.code == 200:
            self.handle_html(url, response.body)

        elif response.code == 599:  # retry
            self._fetching.remove(url)
            self._q.put(url)

    @gen.coroutine
    def get_page(self, url):
        try:
            response = yield self.fetch(url)
            # print('######fetched %s' % url)
        except Exception as e:
            print('Exception: %s %s' % (e, url))
            raise gen.Return(e)
        raise gen.Return(response)

    @gen.coroutine
    def _run(self):
        @gen.coroutine
        def fetch_url():
            current_url = yield self._q.get()
            try:
                if current_url in self._fetching:
                    return

                # print('fetching****** %s' % current_url)
                self._fetching.add(current_url)

                response = yield self.get_page(current_url)
                self.handle_response(current_url, response)  # handle reponse

                self._fetched.add(current_url)

                for i in range(self.concurrency):
                    if self.urls:
                        yield self._q.put(self.urls.pop())

            finally:
                self._q.task_done()

        @gen.coroutine
        def worker():
            while True:
                yield fetch_url()

        self._q.put(self.urls.pop())  # add first url

        # Start workers, then wait for the work queue to be empty.
        for _ in range(self.concurrency):
            worker()

        yield self._q.join(timeout=timedelta(seconds=300000))
        try:
            assert self._fetching == self._fetched
        except AssertionError:
            print(self._fetching - self._fetched)
            print(self._fetched - self._fetching)

    def run(self):
        io_loop = ioloop.IOLoop.current()
        io_loop.run_sync(self._run)


class MySpider(AsySpider):

    def fetch(self, url, **kwargs):
        """重写父类fetch方法可以添加cookies，headers，timeout等信息"""
        headers = {
            "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_3) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/72.0.3626.121 Safari/537.36"
        }
        return super(MySpider, self).fetch(
            url, headers=headers
        )

    def handle_html(self, download_path, c_fule_name, pd_url, content):
        """handle html page"""
        with open(os.path.join(download_path, c_fule_name), 'ab') as f:
            f.write(content)


    def handle_response(self, url, response):
        """inherit and rewrite this method if necessary"""
        download_path, c_fule_name, pd_url, *_ = url
        response.encoding = "utf-8"

        if response.code == 200:
            self.handle_html(download_path, c_fule_name, pd_url, response.body)

        elif response.code == 599:  # retry
            self._fetching.remove(url)
            self._q.put(url)

    @gen.coroutine
    def get_page(self, url):
        download_path, c_fule_name, pd_url, *_ = url

        while True:
            try:
                response = yield self.fetch(pd_url)
                break
            except Exception as e:
                continue
        raise gen.Return(response)


def main(url, download_path, merge):
    try:
        key, file_line = getFileLine(url)
        len_file_line = len(file_line)
        createDownloadFolder(download_path)
        if merge:
            new_file_line = integrityCheck(download_path, file_line)
            if new_file_line:
                process_file_line = processingFileLine(new_file_line, download_path)
                s = MySpider(process_file_line)
                import threading
                p1 = threading.Thread(target=theProgressBar, args=(len_file_line, download_path))
                p1.start()
                s.run()
            else:
                if len(key):  # AES 解密
                    decrptAES(key, file_line, download_path)
                print("合并文件......")
                merge_file(download_path)
    except Exception as e:
        raise e


if __name__ == '__main__':
    merge = ""
    document = ""
    url = ""
    opts, args = getopt.getopt(sys.argv[1:], "u:d:m:")
    if opts:
        for k, v in opts:
            if k == "-u":
                url = v
            if k == "-d":
                document = v
            if k == "-m":
                merge = v
    if document:
        download_path = document
    else:
        download_path = os.getcwd() + "/download"

    if not url:
        print("请输入下载地址")
    else:
        url = url.split("url=")[-1]

        while not checkDownloadFolder(download_path, ".mp4"):
            main(url.replace("https", "http"), download_path, merge)
