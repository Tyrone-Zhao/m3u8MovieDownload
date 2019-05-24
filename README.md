# m3u8MovieDownload
下载m3u8链接电影并自动整合.ts文件

# 使用
**注意：使用前必须先删除下载目录内的mp4文件**

-u -> the m3u8 url

-d -> download_path

-m 1 -> auto merge_file which must be necessary

## 推荐使用:
```sh
$ python3 m3u8Download.py -d /Users/zhaojunyu/Downloads/ -m 1 -u https://cdn-5.haku99.com/hls/2019/05/20/UZWZ2mEs/playlist.m3u8
```

## 备用:
```sh
$ python3 m3u8.py -d /Users/zhaojunyu/Downloads/ -m 1 -u https://cdn-5.haku99.com/hls/2019/05/20/UZWZ2mEs/playlist.m3u8
```