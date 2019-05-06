import os
import platform
import requests
import datetime
from Crypto.Cipher import AES


def download(url):
    download_path = os.getcwd() + "\download"
    if not os.path.exists(download_path):
        os.mkdir(download_path)

    # 新建日期文件夹
    download_path = os.path.join(download_path, datetime.datetime.now().strftime('%Y%m%d_%H%M%S'))
    # print download_path
    os.mkdir(download_path)

    all_content = requests.get(url).text  # 获取第一层M3U8文件内容
    if "#EXTM3U" not in all_content:
        raise BaseException("非M3U8的链接")

    if "EXT-X-STREAM-INF" in all_content:  # 第一层
        file_line = all_content.split("\n")
        for line in file_line:
            if '.m3u8' in line:
                url = url.rsplit("/", 1)[0] + "/" + line  # 拼出第二层m3u8的URL
                all_content = requests.get(url).text

    file_line = all_content.split("\n")

    unknow = True
    key = ""
    for index, line in enumerate(file_line):  # 第二层
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
            unknow = False
            pd_url = url.rsplit("/", 1)[0] + "/" + file_line[index + 1]  # 拼出ts片段的URL
            # print pd_url

            res = requests.get(pd_url)
            c_fule_name = file_line[index + 1].rsplit("/", 1)[-1]

            if len(key):  # AES 解密
                cryptor = AES.new(key, AES.MODE_CBC, key)
                with open(os.path.join(download_path, c_fule_name + ".mp4"), 'ab') as f:
                    f.write(cryptor.decrypt(res.content))
            else:
                with open(os.path.join(download_path, c_fule_name), 'ab') as f:
                    f.write(res.content)
                    f.flush()
    if unknow:
        raise BaseException("未找到对应的下载链接")
    else:
        print("下载完成")

    merge_file(download_path)


def merge_file(path):
    os.chdir(path)
    plat_f = platform.system()
    if "Win" in plat_f:
        cmd = "copy /b * new.tmp"
        os.system(cmd)
        os.system('del /Q *.ts')
        os.system('del /Q *.mp4')
        os.rename("new.tmp", "new.mp4")
    elif "Dar" in plat_f:
        cmd = "cat *.ts > new.ts"
        os.system(cmd)
        os.rename("new.ts", "new.mp4")
        # os.system("ffmpeg -i new.ts -c:v copy -c:a aac new.mp4")
        os.system('rm -f *.ts')


if __name__ == '__main__':
    url = "https://cdn-5.haku99.com/hls/2019/05/06/3KAA7v3y/playlist.m3u8"
    download(url)
