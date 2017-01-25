#!/usr/bin/env python

from __future__ import with_statement

import os
import sys
import errno
import time
import json

from collections import deque
from queue import Queue

from fuse import FUSE, FuseOSError, Operations, LoggingMixIn
from errno import ENOENT

import cherrypy
from ws4py.websocket import WebSocket
from ws4py.server.cherrypyserver import WebSocketPlugin, WebSocketTool

import threading

COMMAND_TYPE = 'command'

websocket_queue = Queue()

class WebSocketFilesystem(LoggingMixIn, Operations):
  def __init__(self):
    cherrypy.config.update({'server.socket_port': 9000})
    WebSocketPlugin(cherrypy.engine).subscribe()
    cherrypy.tools.websocket = WebSocketTool()

    self.ready = False

    class Root(object):
      def __init__(self, wsfs):
        self.wsfs = wsfs

      @cherrypy.expose
      def index(self):
        with open('index.html', 'r') as index_file:
          return index_file.read()

      @cherrypy.expose
      def ws(self):
        # you can access the class instance through
        self.wsfs.ws = cherrypy.request.ws_handler
        self.wsfs.ready = True

    def start_server(q):
      class WSFSWebSocket(WebSocket):
        def __init__(self, sock, protocols=None, extensions=None, environ=None, heartbeat_freq=None):
          super().__init__(sock, protocols=protocols, extensions=extensions, environ=environ, heartbeat_freq=heartbeat_freq)
          self.queue = q

        def received_message(self, message):
          print(message.data)
          self.queue.put(
            json.loads(message.data)
          )

      cherrypy.quickstart(Root(self), '/', config={'/ws': {'tools.websocket.on': True,
                                                     'tools.websocket.handler_cls': WSFSWebSocket}})

    threading.Thread(target=start_server, args=(websocket_queue,)).start()

    print('waiting for ws connection')

    while not self.ready:
      time.sleep(1)
      print('...')

    print('started')

  def receive(self, command):
    response = websocket_queue.get(True, 5)

    if response[COMMAND_TYPE] == command:
      websocket_queue.task_done()
      return response['data']
    else:
      print('oh no: ' + response[COMMAND_TYPE])

  def send(self, data):
    string = json.dumps(data)
    print(string)
    self.ws.send(string)

  # def access(self, path, mode):
  #   full_path = self._full_path(path)
  #   print('access: ' + full_path)
  #   if not os.access(full_path, mode):
  #     raise FuseOSError(errno.EACCES)

  def chmod(self, path, mode):
    self.send(dict(
      command='chmod',
      path=path,
      mode=mode
    ))

    return 0

  def chown(self, path, uid, gid):
    self.send(dict(
      command='chown',
      path=path,
      uid=uid,
      gid=gid
    ))

  def getattr(self, path, fh=None):
    self.send(dict(
      command='getattr',
      path=path
    ))

    attrs = self.receive('getattr')

    if attrs == '':
      raise FuseOSError(ENOENT)

    return attrs

  def readdir(self, path, fh):
    self.send(dict(
      command='readdir',
      path=path
    ))

    dir_files = self.receive('readdir')

    return dir_files

  def readlink(self, path):
    self.send(dict(
      command='readlink',
      path=path
    ))

    link = self.receive('readlink')

    return link['data']

  # def mknod(self, path, mode, dev):
  #   return os.mknod(self._full_path(path), mode, dev)

  def rmdir(self, path):
    self.send(dict(
      command='rmdir',
      path=path
    ))

  def mkdir(self, path, mode):
    self.send(dict(
      command='mkdir',
      path=path,
      mode=mode
    ))

  def statfs(self, path):
    return dict(f_bsize=512, f_blocks=4096, f_bavail=2048)

  def unlink(self, path):
    self.send(dict(
      command='unlink',
      path=path
    ))

  # def symlink(self, name, target):
  #   return os.symlink(name, self._full_path(target))

  def rename(self, old, new):
    self.send(dict(
      command='rename',
      old=old,
      new=new
    ))

  # def link(self, target, name):
  #   return os.link(self._full_path(target), self._full_path(name))

  def utimens(self, path, times=None):
    self.send(dict(
      command='utimens',
      path=path,
      times=times
    ))

  def open(self, path, flags):
    self.send(dict(
      command='open',
      path=path,
      flags=flags
    ))

    open_response = self.receive('open')

    return open_response['fd']

  def create(self, path, mode, fi=None):
    self.send(dict(
      command='create',
      path=path,
      mode=mode
    ))

    create_response = self.receive('create')

    return create_response['fd']

  def read(self, path, length, offset, fh):
    self.send(dict(
      command='read',
      path=path,
      length=length,
      offset=offset
    ))

    read_response = self.receive('read')

    return read_response['data']

  def write(self, path, buf, offset, fh):
    self.send(dict(
      command='write',
      path=path,
      buf=buf,
      offset=offset
    ))

    write_response = self.receive('write')

    return write_response['length']

  def truncate(self, path, length, fh=None):
    self.send(dict(
      command='truncate',
      path=path,
      length=length
    ))

  def flush(self, path, fh):
    return 0

  def release(self, path, fh):
    # closes a fd
    self.send(dict(
      command='release',
      path=path
    ))

  def fsync(self, path, fdatasync, fh):
    return 0

def main(mountpoint):
  print('starting')
  FUSE(WebSocketFilesystem(), mountpoint, nothreads=True, foreground=True)
  print('exiting')

if __name__ == '__main__':
  main(sys.argv[1])
