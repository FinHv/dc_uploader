FROM python:3.13

ARG UNRAR_VERSION=7.1.6
ARG RAR2FS_VERSION=1.29.7

# Update the package list and install necessary packages
RUN wget https://mediaarea.net/repo/deb/repo-mediaarea_1.0-25_all.deb && \
    dpkg -i repo-mediaarea_1.0-25_all.deb && \
    rm repo-mediaarea_1.0-25_all.deb

# Add mtn repo
RUN echo "deb http://download.opensuse.org/repositories/home:/movie_thumbnailer/Debian_12/ /" \
    | tee /etc/apt/sources.list.d/home:movie_thumbnailer.list

RUN curl -fsSL https://download.opensuse.org/repositories/home:movie_thumbnailer/Debian_12/Release.key | gpg --dearmor \
    | tee /etc/apt/trusted.gpg.d/home_movie_thumbnailer.gpg > /dev/null

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    mtn \
    mediainfo \
    fuse3 \
    libfuse-dev \
    screen \
    autoconf

# Install rar2fs
RUN wget https://github.com/hasse69/rar2fs/archive/refs/tags/v${RAR2FS_VERSION}.tar.gz \
    tar zxvf v${RAR2FS_VERSION}.tar.gz

WORKDIR rar2fs-${RAR2FS_VERSION}

RUN wget https://www.rarlab.com/rar/unrarsrc-${UNRAR_VERSION}.tar.gz && tar zxvf unrarsrc-${UNRAR_VERSION}.tar.gz

WORKDIR unrar

RUN make lib && make install-lib

WORKDIR ../

RUN autoreconf -f -i && ./configure && make && make install &&  \
    sed -i 's/#user_allow_other/user_allow_other/g' /etc/fuse.conf

WORKDIR ../

RUN rm -rf rar2fs-${RAR2FS_VERSION}

# Set workdir to the dc_uploader workdir
WORKDIR /dc_uploader

# Set up the virtual enviornment
RUN mkdir -p /venv && python -m venv /venv/dc_uploader
ENV PATH="/venv/dc_uploader/bin:$PATH"
COPY requirements.txt .
RUN /venv/dc_uploader/bin/pip3 install --upgrade pip wheel
RUN /venv/dc_uploader/bin/pip3 install --upgrade -r requirements.txt

COPY . .

RUN find bin/mkbrr -type f -name "mkbrr" -exec chmod +x {} \; chmod +x scripts/*.sh; chmod +x utils/*.sh
RUN chmod 777


ENTRYPOINT bash /dc_uploader/utils/config_validator.sh upload.sh