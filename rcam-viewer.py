#!/usr/bin/env python3
import argparse
import sys
import os
import io
import re
import time
import json
from pprint import pprint

import zmq

import numpy as np
from PIL import Image

from PySide6.QtCore import Qt, QThread, Signal, Slot
from PySide6.QtGui import QActionGroup, QAction, QImage, QKeySequence, QPixmap
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QSizePolicy
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QVBoxLayout, QGroupBox, QTabWidget
from PySide6.QtWidgets import QGroupBox, QPushButton, QLabel, QLineEdit, QCheckBox

from PySide6.QtCharts import QChart, QChartView
from PySide6.QtCharts import QBarSeries, QBarSet, QBarCategoryAxis, QValueAxis
from PySide6.QtGui import QPainter

from rcam.server import PubSubCommands
from rcam import RCamClient


class Worker(QThread):
    update_image = Signal(int, np.ndarray)
    update_metadata = Signal(int, str)

    def __init__(self, parent, zmq_context, pub_url):
        QThread.__init__(self, parent)
        # initial state
        self._over = False
        self._paused = True

        # connect to the publisher
        self.pub_url = pub_url
        
        self.sub_sock = zmq_context.socket(zmq.SUB)
        self.sub_sock.set_hwm(2)
        self.sub_sock.connect(self.pub_url)
        self.sub_sock.setsockopt(zmq.SUBSCRIBE, b'')
        
        # the inproc sockets for gui<->worker comms
        self.receiver = zmq_context.socket(zmq.PAIR)
        self.receiver.bind("inproc://worker")
        
        self.sender = zmq_context.socket(zmq.PAIR)
        self.sender.connect("inproc://worker")
        
        self.over_msg = "over".encode('utf-8')
        self.size_msg = "size".encode('utf-8')
        self.pause_msg = "pause".encode('utf-8')
        self.resume_msg = "resume".encode('utf-8')
        
    def run(self):
        poller = zmq.Poller()
        poller.register(self.sub_sock, zmq.POLLIN)
        poller.register(self.receiver, zmq.POLLIN)
        
        while not self._over:
            events = poller.poll(200)
            if len(events) == 0:
                continue
            
            for sock, mask in events:
                if sock == self.receiver:
                    self._handle_cmd()
                elif sock == self.sub_sock:
                    self._handle_sub()
        
        self.sub_sock.disconnect(self.pub_url)
                
    def _handle_cmd(self):
        tag, d0, d1 = self.receiver.recv_multipart()
        if tag == self.over_msg:
            self._over = True
        
        elif tag == self.pause_msg:
            self._paused = True
        
        elif tag == self.resume_msg:
            self._paused = False
    
    def _handle_sub(self):
            tag, idx, data = self.sub_sock.recv_multipart()
            
            # if we're paused, receive the message but do nothing with it
            if self._paused:
                return

            # not paused, so handle the message
            idx = int(idx.decode('utf-8'))

            if tag == PubSubCommands.METADATA:
                metadata = data.decode('utf-8')
                self.update_metadata.emit(idx, metadata)
            
            elif tag == PubSubCommands.JPEGIMG:
                image_id = f'img-{idx:04d}'
            
                jpeg = io.BytesIO(data)
                image = np.array(Image.open(jpeg))
                
                # and send it to the GUI thread
                self.update_image.emit(idx, image)

    def set_over(self):
        self.sender.send_multipart([self.over_msg, b'', b''])
        
    def pause(self):
        self.sender.send_multipart([self.pause_msg, b'', b''])
    
    def resume(self):
        self.sender.send_multipart([self.resume_msg, b'', b''])


class MainWindow(QMainWindow):

    def __init__(self, api_url, pub_url):
        super().__init__()
        self.setWindowTitle("RaspberryAstro")
        
        # build the interface
        self._build_interface()

        # track the latest metadata and images
        self.idx = 0
        self.metadata = None
        self.image = None
        self.locked = False
        
        # create the worker and command
        self.zmq_context = zmq.Context()
        
        self.worker = Worker(self, self.zmq_context, pub_url)
        self.worker.update_image.connect(self.update_image)
        self.worker.update_metadata.connect(self.update_metadata)
        self.worker.start()
                
        self.cam_api = RCamClient(self.zmq_context, api_url)
        
        # put the server into the same state as the GUI
        self.cam_api.fit_scaled()
        
        # handle the quit event from the window manager
        QApplication.instance().aboutToQuit.connect(self.stop_thread)

    ## slots
    
    @Slot(int, str)
    def update_metadata(self, idx, metadata):
        self.idx = idx
        self.metadata = json.loads(metadata)

        metajson = json.dumps(self.metadata, sort_keys=True, indent=4)
        self.metaview.setText(metajson)
        
        if (af_enabled := self.metadata.get('AfEnable', None)) is not None:
            if af_enabled != self.af_action.isChecked():
                self.af_action.setChecked(af_enabled)

        if (ae_enabled := self.metadata.get('AeEnable', None)) is not None:
            if ae_enabled != self.ae_action.isChecked():
                self.ae_action.setChecked(ae_enabled)

        if (awb_enabled := self.metadata.get('AwbEnable', None)) is not None:
            if awb_enabled != self.awb_action.isChecked():
                self.awb_action.setChecked(awb_enabled)

    @Slot(int, np.ndarray)
    def update_image(self, idx, image):
        self.idx = idx
        self.image = image  # numpy ndarray
        
        self.image_label.setText(f"{idx:04d}")

        if self.tabw.currentIndex() == 0:
            self.redraw_image()
        else:
            self.redraw_histogram()
    
    def redraw_image(self):
        # create the qimage
        ih, iw, ch = self.image.shape
        img = QImage(self.image.data, iw, ih, ch * iw, QImage.Format_RGB888)
        
        # scale the image to the view size
        vw, vh = self.image_view.width(), self.image_view.height()
        scaled_img = img.scaled(vw, vh, Qt.KeepAspectRatio)
        
        # display it
        pixmap = QPixmap.fromImage(scaled_img)
        self.image_view.setPixmap(pixmap)
        
        # check the image size
        if ih > vh or iw > vw:
            self.cam_api.set_size(vw, vh)
    
    def redraw_histogram(self):
        xstart = int(self.image.shape[1]/2 - 256)
        ystart = int(self.image.shape[0]/2 - 256)
        histo_image = self.image[ystart:ystart+512, xstart:xstart+512, :]
        histogram, edges = np.histogram(histo_image, bins=25, range=[0, 255])
        
        for idx, val in enumerate(histogram):
            self.bars.replace(idx, min(val, 100000))
    
    @Slot(bool)
    def fit_scaled(self, enabled):
        if enabled:
            self.cam_api.fit_scaled()

    @Slot(bool)
    def fit_cropped(self, enabled):
        if enabled:
            self.cam_api.fit_cropped()

    @Slot(bool)
    def auto_focus(self, af_enable):
        self.cam_api.auto_focus(af_enable)
    
    @Slot()
    def run_autofocus(self):
        self.cam_api.run_autofocus()
    
    @Slot()
    def increase_lens_position(self):
        self.cam_api.increase_lens_position()
    
    @Slot()
    def decrease_lens_position(self):
        self.cam_api.decrease_lens_position()

    @Slot(bool)
    def auto_exposure(self, ae_enable):
        self.cam_api.auto_exposure(ae_enable)

    @Slot(bool)
    def toggle_exposure_lock(self, locked):
        self.locked = not self.locked
    
    @Slot()
    def increase_exposure_time(self):
        self.ae_action.setChecked(False)
        self.cam_api.etime_increase(self.locked)

    @Slot()
    def decrease_exposure_time(self):
        self.ae_action.setChecked(False)
        self.cam_api.etime_decrease(self.locked)

    @Slot()
    def increase_gain(self):
        self.ae_action.setChecked(False)
        self.cam_api.gain_increase(self.locked)

    @Slot()
    def decrease_gain(self):
        self.ae_action.setChecked(False)
        self.cam_api.gain_decrease(self.locked)

    @Slot(bool)
    def auto_whitebalance(self, awb_enable):
        self.cam_api.auto_whitebalance(awb_enable)

    @Slot()
    def increase_red_gain(self):
        self.awb_action.setChecked(False)
        self.cam_api.red_gain_increase()

    @Slot()
    def decrease_red_gain(self):
        self.awb_action.setChecked(False)
        self.cam_api.red_gain_decrease()

    @Slot()
    def increase_blue_gain(self):
        self.awb_action.setChecked(False)
        self.cam_api.blue_gain_increase()

    @Slot()
    def decrease_blue_gain(self):
        self.awb_action.setChecked(False)
        self.cam_api.blue_gain_decrease()

    @Slot()
    def stop_thread(self):
        self.worker.set_over()
        self.worker.wait()
        
    @Slot()
    def pause_resume(self):
        if self.pr_button.text() == "Pause":
            self.worker.pause()
            self.pr_button.setText("Resume")
        else:
            self.worker.resume()
            self.pr_button.setText("Pause")
    
    @Slot()
    def exit(self):
        self.stop_thread()
        self.close()

    ## event handlers
    
    def resizeEvent(self, event):
        super().resizeEvent(event)
        
        # only respond to spontaneous events... that is, events triggered
        #   by something external to the application such as the user resizing
        #   the window
        if not event.spontaneous():
            return
        
        # notify the server of the new image size
        self.cam_api.set_size(self.image_view.width(), self.image_view.height())
        
        # if we have an image, redisplay it at the new size
        if self.image is not None:
            self.update_image(self.idx, self.image)
    
    def showEvent(self, event):
        super().showEvent(event)
        self.worker.resume()
    
    def hideEvent(self, event):
        super().hideEvent(event)
        self.worker.pause()

    ## interface building

    def _build_interface(self):
        # setup initial size
        self.setGeometry(QApplication.instance().primaryScreen().availableGeometry())
        
        # build the menus
        self._build_file_menu()
        self._build_image_menu()
        self._build_focus_menu()
        self._build_exposure_menu()
        self._build_whitebalance_menu()

        # main window area
        central = QWidget(self)
        
        tl_layout = self._build_top_left()
        tr_layout = self._build_top_right()
        bl_layout = self._build_bottom_left()
        br_layout = self._build_bottom_right()
                
        layout = QGridLayout(central)
        layout.addLayout(tl_layout, 0, 0)
        layout.addLayout(tr_layout, 0, 1)
        layout.addLayout(bl_layout, 1, 0)
        layout.addLayout(br_layout, 1, 1)
        
        layout.setRowStretch(0, 1)
        layout.setColumnStretch(0, 1)

        # central.setLayout(layout)
        self.setCentralWidget(central)
    
    def _build_file_menu(self):
        mb = self.menuBar()
        file_menu = mb.addMenu("File")
        file_menu.addAction(
            QAction("Exit", self, triggered=self.exit)
        )

    def _build_image_menu(self):
        mb = self.menuBar()
        view_menu = mb.addMenu("Image")
        
        qag = QActionGroup(self)
        
        self.v_scale = QAction("Scale to Fit", self, shortcut="Ctrl+S", checkable=True, triggered=self.fit_scaled)
        qag.addAction(self.v_scale)

        self.v_crop = QAction("Crop to Fit", self, shortcut="Ctrl+C", checkable=True, triggered=self.fit_cropped)
        qag.addAction(self.v_crop)
        
        self.v_scale.setChecked(True)

        view_menu.addAction(self.v_scale)
        view_menu.addAction(self.v_crop)

    def _build_focus_menu(self):
        mb = self.menuBar()
        focus_menu = mb.addMenu("Focus")
        
        self.af_action = QAction("Auto Focus", self, shortcut="Ctrl+F", checkable=True, triggered=self.auto_focus)
        focus_menu.addAction(self.af_action)
        
        focus_menu.addSeparator()
        focus_menu.addAction(
            QAction("Run Auto Focus", self, shortcut="Ctrl+Shift+F", triggered=self.run_autofocus)
        )

        focus_menu.addSeparator()
        focus_menu.addAction(
            QAction("Increase Lens Position", self, shortcut="Ctrl+Shift+L", triggered=self.increase_lens_position)
        )
        focus_menu.addAction(
            QAction("Decrease Lens Position", self, shortcut="Ctrl+L", triggered=self.decrease_lens_position)
        )

    def _build_exposure_menu(self):
        mb = self.menuBar()
        exp_menu = mb.addMenu("Exposure")
        
        self.ae_action = QAction("Auto Exposure", self, shortcut="Ctrl+E", checkable=True, triggered=self.auto_exposure)
        exp_menu.addAction(self.ae_action)

        exp_menu.addSeparator()
        exp_menu.addAction(
            QAction("Manual Exposure Locked", self, shortcut="Ctrl+M", checkable=True, triggered=self.toggle_exposure_lock)
        )

        exp_menu.addSeparator()
        exp_menu.addAction(
            QAction("Increase Exposure Time", self, shortcut="Ctrl+Shift+T", triggered=self.increase_exposure_time)
        )
        exp_menu.addAction(
            QAction("Decrease Exposure Time", self, shortcut="Ctrl+T", triggered=self.decrease_exposure_time)
        )

        exp_menu.addSeparator()
        exp_menu.addAction(
            QAction("Increase Gain", self, shortcut="Ctrl+Shift+G", triggered=self.increase_gain)
        )
        exp_menu.addAction(
            QAction("Decrease Gain", self, shortcut="Ctrl+G", triggered=self.decrease_gain)
        )

    def _build_whitebalance_menu(self):
        mb = self.menuBar()
        wb_menu = mb.addMenu("White Balance")
        
        self.awb_action = QAction("Auto White Balance", self, shortcut="Ctrl+W", checkable=True, triggered=self.auto_whitebalance)
        wb_menu.addAction(self.awb_action)

        wb_menu.addSeparator()
        wb_menu.addAction(
            QAction("Increase Red Gain", self, shortcut="Ctrl+Shift+R", triggered=self.increase_red_gain)
        )
        wb_menu.addAction(
            QAction("Decrease Red Gain", self, shortcut="Ctrl+R", triggered=self.decrease_red_gain)
        )

        wb_menu.addSeparator()
        wb_menu.addAction(
            QAction("Increase Blue Gain", self, shortcut="Ctrl+Shift+B", triggered=self.increase_blue_gain)
        )
        wb_menu.addAction(
            QAction("Decrease Blue Gain", self, shortcut="Ctrl+B", triggered=self.decrease_blue_gain)
        )
    
    def _build_top_left(self):
        self.tabw = QTabWidget(self)
        page1 = self._build_page1()
        page2 = self._build_page2()
        
        self.tabw.addTab(page1, "Image")
        self.tabw.addTab(page2, "Histogram")
        
        layout = QVBoxLayout()
        layout.addWidget(self.tabw)
        return layout
    
    def _build_page1(self):
        self.image_view = QLabel()
        self.image_view.setAlignment(Qt.AlignCenter)
        self.image_view.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        return self.image_view
    
    def _build_page2(self):
        self.bars = QBarSet("Buckets")
        self.bars.append([0 for x in range(25)])
        
        series = QBarSeries()
        series.append(self.bars)
        
        chart = QChart()
        chart.addSeries(series)
        chart.setTitle("Image Centre Histogram")
        
        categories = [str(x) for x in range(25)]
        axis_x = QBarCategoryAxis()
        axis_x.append(categories)
        chart.addAxis(axis_x, Qt.AlignBottom)
        series.attachAxis(axis_x)

        axis_y = QValueAxis()
        axis_y.setRange(0, 100000)
        chart.addAxis(axis_y, Qt.AlignLeft)
        series.attachAxis(axis_y)

        chart.legend().setVisible(True)
        chart.legend().setAlignment(Qt.AlignBottom)

        chart_view = QChartView(chart)
        chart_view.setRenderHint(QPainter.Antialiasing)
        
        return chart_view
    
    def _build_top_right(self):
        self.meta_group = QGroupBox("Metadata")
        meta_layout = QVBoxLayout(self.meta_group)
        self.metaview = QLabel()
        self.metaview.setFixedWidth(260)
        self.metaview.setTextInteractionFlags(Qt.TextSelectableByMouse)
        meta_layout.addWidget(self.metaview)

        layout = QVBoxLayout()
        layout.addWidget(self.meta_group)
        layout.addStretch(stretch=1)
        return layout
    
    def _build_bottom_left(self):
        self.image_label = QLabel("0000")
        self.image_label.setAlignment(Qt.AlignCenter)
        
        layout = QHBoxLayout()
        layout.addWidget(self.image_label)
        return layout
    
    def _build_bottom_right(self):
        self.pr_button = QPushButton("Pause")
        self.pr_button.clicked.connect(self.pause_resume)
        quit_button = QPushButton("Quit")
        quit_button.clicked.connect(self.exit)

        layout = QHBoxLayout()
        layout.addWidget(self.pr_button)
        layout.addWidget(quit_button)
        return layout


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('api_url', help='the api url to connect to', type=str)
    args = parser.parse_args()

    app = QApplication(sys.argv)
    app.setStyle("fusion")

    tcp_re = re.compile("^tcp://(?P<address>.+?):(?P<port>\d+)$")
    mo = tcp_re.match(args.api_url)
    if mo is None:
        raise ValueError(f"unable to parse {args.api_url}")
    address = mo['address']
    port = int(mo['port'])

    pub_url = f"tcp://{address}:{port+1}"

    w = MainWindow(args.api_url, pub_url)
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
