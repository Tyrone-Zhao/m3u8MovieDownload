import os
import re
import sys
import time
import numpy
import getopt
import asyncio
import platform
import requests
from tqdm import tqdm
from pathlib import Path
from Crypto.Cipher import AES
from collections import OrderedDict
from multiprocessing import Process, cpu_count

headers = {
    "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_3) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/72.0.3626.121 Safari/537.36"
}


def processStart(url_list):
    tasks = []
    loop = asyncio.get_event_loop()
    for url in url_list:
        if url:
            tasks.append(asyncio.ensure_future(yourFunc(url)))
    loop.run_until_complete(asyncio.wait(tasks))


def tasksStart(url_list):
    # 进程池进程数量
    cpu_num = cpu_count()
    if len(url_list) <= cpu_num:
        processes = []
        for i in range(len(url_list)):
            url = url_list[i]
            url_list_new = [url]
            p = Process(target=processStart, args=(url_list_new,))
            processes.append(p)
        for p in processes:
            p.start()
    else:
        coroutine_num = len(url_list) // cpu_num
        processes = []
        url_list += [""] * (cpu_num * (coroutine_num + 1) - len(url_list))
        data = numpy.array(url_list).reshape(coroutine_num + 1, cpu_num)
        for i in range(cpu_num):
            url_list = data[:, i]
            p = Process(target=processStart, args=(url_list,))
            processes.append(p)
        for p in processes:
            p.start()
    return processes


async def yourFunc(line):
    await downloadM3u8(line)


def multiProcessAsync(url_list):
    return tasksStart(url_list)


def createDownloadFolder(download_path):
    """ 创建下载目录 """
    if not os.path.exists(download_path):
        os.mkdir(download_path)

    # # 新建日期文件夹
    # download_path = os.path.join(download_path) + "/" + datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    # if not os.path.exists(download_path):
    #     os.mkdir(download_path)


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


async def downloadM3u8(line):
    """ 根据file_line下载m3u8文件 """
    key, download_path, c_fule_name, pd_url, *_ = line

    res = requests.get(pd_url)
    res.encoding = "utf-8"
    try:
        if len(key):  # AES 解密
            with open(os.path.join(download_path, c_fule_name), 'ab') as f:
                cryptor = AES.new(key, AES.MODE_CBC, key)
                text = cryptor.decrypt(res.content)
                f.write(text)
        else:
            with open(os.path.join(download_path, c_fule_name), 'ab') as f:
                f.write(res.content)
    except ValueError:
        # with open(os.path.join(download_path, "error.txt"), 'ab') as f:
        #     f.write(res.content)
        #     f.write("\n")
        pass


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


def processingFileLine(key, file_line, download_path):
    """ 把file_line变成(url, download_path, line)的元组形式list """
    res = []
    for f_name, f_url in file_line.items():
        res.append((key, download_path, f_name, f_url))

    return res


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


def theProgressBar(len_file_line, download_path):
    """ 显示进度条 """
    temp = checkDownloadFolder(download_path, ".ts")

    for i in tqdm(range(len(temp), len_file_line)):
        while True:
            temp = checkDownloadFolder(download_path, ".ts")
            if len(temp) >= i:
                break


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


def main(url, download_path, merge, begin):
    """ 下载ts文件并自动整合，包括开启进度条 """
    try:
        key, file_line = getFileLine(url)
        len_file_line = len(file_line)
        createDownloadFolder(download_path)
        if merge:
            new_file_line = integrityCheck(download_path, file_line)
            if new_file_line:
                process_file_line = processingFileLine(key, new_file_line, download_path)
                processes = multiProcessAsync(process_file_line)
                if begin == 1:
                    theProgressBar(len_file_line, download_path)
            else:
                print("下载完成，合并文件......")
                merge_file(download_path)
    except Exception as e:
        raise e


if __name__ == "__main__":
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
        begin = 1

        while not checkDownloadFolder(download_path, ".mp4"):
            main(url.replace("https", "http"), download_path, merge, begin)
            begin += 1
