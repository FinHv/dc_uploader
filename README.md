# Still under development

## What is DC Uploader?

A simple python tool built for ubuntu to create and upload torrents. Debian is unsupported at the moment but hopefully will be soon.

- Checks for duplicates.
- Creates torrents.
- Automatically adds uploaded torrent to client by copying the created .torrent file to client watch directory.
- Takes screenshots with movie thumbnailer and uploads to image host.
  - Works on rar'd content as well. Only done when no sample is found.
- Added the mediainfo to the uploaded torrent.
- Automatically enable HTTPS with either certbot (installed via pip) or a self-signed certificate.
    - Support for cloudflare DNS challenge via cloudflare API token.
    - Sets up automatic certbot cert renewal and certbot updates, if not already existing.
- Gets video game information from IGDB (API key required).
- Gets movie/show information from TMDB (API key required).
- Automatically edit .torrent from source content tracker instead of generating new .torrent with torf.

## Install

1. Download the project as a zip.

2. Unzip to desired directory.

3. Run install.sh, an interactive install script which will install the necessary packages and python virtual environments.

4. Modify config.ini with at least the following information. Web server will not start if the directories for these settings do not exist. The rest can be set via the web UI.
    - ETORFPATH
    - DATADIR
    - WATCHFOLDER

5. Run start.sh
6. Nagivate to https://[hostname.domain]:5000, assuming you used the default port. If you specified a different port during install, use that.
7. Login with your specified username/password
8. Update the relevant settings as needed
9. You're ready to upload now!

### Important config.ini settings

Here are some important settings you can find in the config.ini. Do not change the headers or location of the settings.

- CAPTCHA_PASSKEY: This is your passkey for the site.
- ETORFPATH: directory where .torrent files from source torrent site are downloaded to. If you are rehashing new .torrent files when you upload (e.g. EDIT_TORRENT is set to false), this directory is largely irrelevant and can be set to a dummy directory.
    - If EDIT_TORRENT is set to true, it will edit the torrent instead of creating a new one, which saves time.
- ANNOUNCEURL: Your personal announce URL.
- WATCHFOLDER: Path to the directory where .torrent file for the uploaded torrent is placed for the client to import, e.g., /uploaders/torrentwatch.
- DATADIR: Path to where the downloaded torrent data is stored, e.g., /uploaders/complete. If you like to sort your downloads into tracker/category/etc specific directory (e.g. due to using an *arr stack), see [below](https://github.com/FinHv/dc_uploader/new/main?filename=README.md#discrete-directories).
- FILTERS: Should not be changed. Default is files/filters.json.
- UPLOADLOG: Log file for uploads, default is files/upload.log.
- COOKIE_PATH: Temporary file for cookies, default is files/cookies.tmp.

TMDB:
- APIKEY: Used for TMDB lookups. See [here](https://developer.themoviedb.org/docs/getting-started#:~:text=To%20register%20for%20an%20API,to%20our%20terms%20of%20use.) on how to get an API key.

IGDB:
- CLIENT_ID and CLIENT_SECRET: Used for IGDB integration. See [here](https://api-docs.igdb.com/#getting-started) on how to generate a client ID and secret.

## Usage

start.sh will start the web server on the specified port specified during install. Starts in a detatched screen session named "dcc-uploader".

shutdown.sh shuts down the web server and ends the screen session.

### upload.sh usage for manual uploading via command line

#### upload.sh "/full/path/to/torrent/directory" [OPTION]

Let's say you have a directory you would like to upload:

/home/torrentdata/this.is.a.nice.movie-grp

With the actual movie inside being:

/home/torrentdata/this.is.a.nice.movie-grp/this.is.a.nice.movie-grp.mkv

The DATADIR would be /home/torrentdata

You would run: `upload.sh "/home/torrentdata/tracker1/this.is.a.nice.movie-grp"`

By default, the program assumes that the data to be uploaded already exists in DATADIR. See optional arguments if you wish to modify this behavior.

#### Optional arguments:
-h, --help: Prints help. Called via `upload.sh -h` or `upload.sh --help`.

Following arguments are primarily used when user is using discrete directories.

-l, --link: Hardlinks provided directory to DATADIR. If hardlink fails, fallback to symlink.

-c, --copy: Copies provided directory to DATADIR

-m, --move: Moves provided directory to DATADIR

### Web app usage

Ensure DATADIR is set properly in the config.ini. Then, just click "upload".

If using discrete directories, web app requires users to manually copy/hardlink/symlink/move to DATADIR. Hopefully future versions will automate the copy/hardlink/symlink process when using discrete directory. 

## Discrete directories

If you just download all your torrents to one directory, just set DATADIR to that directory and ignore this section. For those who keep their torrent directories neat, read on.

Let's say you have sorted your downloaded torrents into neat little discrete directories, such as based on category, tracker, etc, you'll need to use the linking option (enabled by default).

What this means is that, you will need to create a upload specific directory to use as the DATADIR. For example, you have your torrents sorted into two directories:

/data/movie/someneatmovie/someneatmovie.mkv

/data/tv/someneatshow/someneatshows01e01.mkv,someneatshows01e02.mkv,etc

DATADIR can't be both /data/movie *and* /data/tv at the same time, so what do you do? You create:

/data/uploads

Now, you set DATADIR to /data/uploads, and --link,--copy, or --mv become non-optional arguments. You must pick one. Then, if you run the upload script with your chosen option on /data/movie/someneatmovie, it will hardlink/symlink/copy/move /data/movie/someneatmovie to /data/uploads, resulting in a final directory of /data/uploads/someneatmovie with someneatmovie.mkv inside the someneatmovie directory. If you use --link, this results in a second copy of the file that takes no disk space. Also known as black magic.

The alternative is to update config.ini's DATADIR every time you want to upload from a different directory, but who wants to do that?

## Uninstall

To remove just the program, simply delete the program folder.

To remove the python virtual environment, simply delete the virtual environment folder specified during install

To remove the dependencies installed via apt, run:

`apt remove build-essential mtn mediainfo libfuse-dev screen software-properties-common autoconf && apt autoremove -y`

To remove rar2fs:

`rm /usr/local/bin/rar2fs`



## FAQ

#### Q: After my torrent is uploaded, where does the actual torrent in the client expect the data to be?

A: This depends on how you set up the watch directory. By using a watch directory, the client adds the .torrent file to the client similar to a user adding a torrent.

#### Q: I use discrete directories, but I want to add it to a download-then-uploadToDCC automation pathway, how do I do that?

A: Assuming you have created an upload directory as directed by the [discrete directories](https://github.com/FinHv/dc_uploader/new/main?filename=README.md#discrete-directories) section, just pass the torrent content path to upload.sh similar to how you would call upload.sh from the command line. The actual upload script or underlying upload.py do not require user intervention to begin with.

#### Q: Can I pass a file to the script rather than a directory?

Yes, there's checks for that, but it could introduce bugs. The tool is designed primarily with the expectation that the user will pass the script the directory holding the data to be uploaded as a torrent, unlike [Audionut's Upload Assistant](https://github.com/Audionut/Upload-Assistant) which can take either directories or files.

#### Q: What happens if I pass the script a file instead of a directory/directory?

A: A polar bear mauls you. Assuming you survive, for discrete directory users, the script will create a directory in DATADIR with the file name as the directory name, minus the file extension, and copy/hardlink/symlink the file to that directory. For non-discrete directory users,

#### Q: What happens if I pass the script the path of something already in DATADIR?

A: **This is what folks not using discrete directory are doing anyways, so this answer is mostly relevant to discrete directory users.** If you pass it a directory, it'll proceed as normal and not create/copy anything. The script will detect that the directory already exists and be happy. 

If you pass it a *file* that exists in DATADIR, it will create a directory named the same as the filename and then hardlink/symlink the file into that directory. If the directory the script wants to create already exists, it'll omit creating the directory altogether, and simply attempt to use the directory that was just found, even if it is an empty directory.

You should avoid passing files that exist in DATADIR to begin with as it may introduce bugs and will result in a duplicate file, and instead simply rely on --l, --c, or --m instead. That said, the duplicate file will not take up any additional space, but again, avoid.

#### Q: Why hardlink/symlink if file already exists in DATADIR? Why not move it?

A: The data isn't moved because it might be used by another torrent.

#### Q: When does the tool fallback to symlinking?

A: The primary limitation of hardlinking is that the source and intended destination must be on the same filesystem - e.g. it can't hardlink from one harddrive to another, from one harddrive to a SMB/NFS mount, etc. When the tool detects that a hardlink can't be done, it tries again using symlinks.

### Q: Can I use this tool on windows?

A: Maybe, but most likely not. While built on python, it does rely quite a bit on assumptions specific to Linux. The bash scripts certainly will not work. Instead, look into [WSL](https://learn.microsoft.com/en-us/windows/wsl/install). Once WSL is running, just mount your torrent parent folder to the WSL environment through /etc/fstab and you should be fine. Treat it like a second computer.

### Q: I used certbot to get certificates, does it renew for me?

A: No, unless you've previously set up renewal yourself. The install script does not set up renewal for you. If you want to set up automatic renewal, run