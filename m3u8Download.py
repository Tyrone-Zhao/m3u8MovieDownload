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
from collections import OrderedDict
from Crypto.Cipher import AES
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


def getFileLine(url):
    """ 获取file_url, 即所有m3u8文件的url地址 """
    all_content = requests.get(url).text  # 获取第一层M3U8文件内容
    if "#EXTM3U" not in all_content:
        raise BaseException("非M3U8的链接")

    if "EXT-X-STREAM-INF" in all_content:  # 第一层
        file_line = all_content.split("\n")
        for line in file_line:
            if '.m3u8' in line:
                url = url.rsplit("/", 1)[0] + "/" + line  # 拼出第二层m3u8的URL
                with open("breakpoint.txt", "w") as f:
                    f.write(url)
                all_content = requests.get(url).text

    file_line = all_content.split("\n")

    http = r'((http|ftp|https)://(([a-zA-Z0-9\._-]+\.[a-zA-Z]{2,6})|([0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3})))'
    url_head = re.findall(http, "https://v2.bajiebofang.com/ppvod/8071A2CEA071459EDD41F82F1317DB04.m3u8")[0][0]
    res = OrderedDict()
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
                pd_url = url_head + "/" + file_line[index + 1]  # 拼出ts片段的URL

            c_fule_name = file_line[index + 1].rsplit("/", 1)[-1]
            res[c_fule_name] = pd_url

    return key, res


async def downloadM3u8(line):
    """ 根据file_line下载m3u8文件 """
    key, download_path, c_fule_name, pd_url, *_ = line

    res = requests.get(pd_url)

    try:
        if len(key):  # AES 解密
            cryptor = AES.new(key, AES.MODE_CBC, key)
            with open(os.path.join(download_path, c_fule_name + ".mp4"), 'ab') as f:
                f.write(cryptor.decrypt(res.content))
        else:
            with open(os.path.join(download_path, c_fule_name), 'ab') as f:
                f.write(res.content)
    except Exception:
        print(f"{line}下载失败")
        os.chdir(download_path)
        plat_f = platform.system()
        if "Win" in plat_f:
            os.system(f'del /Q {c_fule_name}')
        elif "Dar" in plat_f:
            os.system(f'rm -f {c_fule_name}')
        print(f"{line}不完整文件已删除")


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


def integrityCheck(url, down):
    """ 检查是否有缺失的.ts文件，如有则重新下载 """
    key, file_line = getFileLine(url)
    download_path = down
    temp = checkDownloadFolder(download_path, ".ts")

    if temp:
        max_num = 0
        res = []
        for t in temp:
            filepath, tempfilename = os.path.split(t)
            filename, extension = os.path.splitext(tempfilename)
            num = ""
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
            del file_line[r]

    return file_line


def theProgressBar(download_path):
    """ 显示进度条 """
    key, file_line = getFileLine(url)
    temp = checkDownloadFolder(download_path, ".ts")

    res = len(file_line)
    for i in tqdm(range(len(temp), res)):
        t = time.time()
        while True:
            temp = checkDownloadFolder(download_path, ".ts")
            if len(temp) >= i:
                break
            if time.time() - t > 180:
                print("网速太慢，程序转入后台下载")
                return


def checkDownloadFolder(download_path, ty=".ts"):
    """ 返回下载目录中的文件list """
    temp = []
    try:
        temp += [os.path.abspath(p) for p in Path(download_path).glob(f'**/*{ty}')]
    except PermissionError:
        pass

    def sortNum(name):
        num = ""
        for n in name:
            if n.isdigit():
                num += n
        return int(num)

    return sorted(temp, key=sortNum)


def main(url, download_path, merge):
    try:
        key, file_line = getFileLine(url)
        createDownloadFolder(download_path)
        if merge:
            file_line = integrityCheck(url, download_path)
            if file_line:
                file_line = processingFileLine(key, file_line, download_path)
                processes = multiProcessAsync(file_line)
                theProgressBar(download_path)
                for p in processes:
                    p.join()
            else:
                print("开始合并文件")
                merge_file(download_path)
    except Exception as e:
        raise


if __name__ == "__main__":
    merge = ""
    document = ""
    url = "https://cdn-5.haku99.com/hls/2019/05/20/UZWZ2mEs/playlist.m3u8"
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

    while not checkDownloadFolder(download_path, ".mp4"):
        main(url.replace("https", "http"), download_path, merge)
