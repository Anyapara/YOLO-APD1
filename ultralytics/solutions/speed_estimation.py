# Ultralytics YOLO 🚀, AGPL-3.0 license

from collections import defaultdict
from time import time

import cv2
import numpy as np

from ultralytics.utils.checks import check_imshow
from ultralytics.utils.plotting import Annotator, colors


class SpeedEstimator:
    """A class to estimate the speed of objects in a real-time video stream based on their tracks."""

    def __init__(self, names, reg_pts=None, view_img=False, line_thickness=2, spdl_dist_thresh=10):
        """
        Initializes the SpeedEstimator with the given parameters.

        Args:
            names (dict): Dictionary of class names.
            reg_pts (list, optional): List of region points for speed estimation. Defaults to [(20, 400), (1260, 400)].
            view_img (bool, optional): Whether to display the image with annotations. Defaults to False.
            line_thickness (int, optional): Thickness of the lines for drawing boxes and tracks. Defaults to 2.
            spdl_dist_thresh (int, optional): Distance threshold for speed calculation. Defaults to 10.
        """
        self.view_img = view_img    # bool for displaying inference

        # Region information
        self.reg_pts = reg_pts if reg_pts is not None else [(20, 400), (1260, 400)]

        # Tracking information
        self.names = names
        self.tf = line_thickness
        self.trk_history = defaultdict(list)

        # Speed estimation information
        self.current_time = 0
        self.spd = {}       # set for speed data
        self.trkd_ids = []  # list for already speed_estimated and tracked ID's
        self.spdl = spdl_dist_thresh    # Speed line distance threshold
        self.trk_pt = {}    # set for tracks previous time
        self.trk_pp = {}    # set for tracks previous point

        # Check if the environment supports imshow
        self.env_check = check_imshow(warn=True)

    def calculate_speed(self, trk_id, track):
        """
        Calculates the speed of an object.

        Args:
            trk_id (int): Object track id.
            track (list): Tracking history for drawing tracks path.
        """
        if not self.reg_pts[0][0] < track[-1][0] < self.reg_pts[1][0]:
            return
        if self.reg_pts[1][1] - self.spdl < track[-1][1] < self.reg_pts[1][1] + self.spdl:
            direction = "known"
        elif self.reg_pts[0][1] - self.spdl < track[-1][1] < self.reg_pts[0][1] + self.spdl:
            direction = "known"
        else:
            direction = "unknown"

        if self.trk_pt.get(trk_id) != 0 and direction != "unknown" and trk_id not in self.trkd_ids:
            self.trkd_ids.append(trk_id)

            time_difference = time() - self.trk_pt[trk_id]
            if time_difference > 0:
                self.spd[trk_id] = np.abs(track[-1][1] - self.trk_pp[trk_id][1]) /time_difference

        self.trk_pt[trk_id] = time()
        self.trk_pp[trk_id] = track[-1]

    def estimate_speed(self, im0, tracks):
        """
        Estimates the speed of objects based on tracking data.

        Args:
            im0 (ndarray): Image.
            tracks (list): List of tracks obtained from the object tracking process.

        Returns:
            (ndarray): The image with annotated boxes and tracks.
        """
        if tracks[0].boxes.id is None:
            if self.view_img and self.env_check:
                self.display_frames()
            return im0

        boxes = tracks[0].boxes.xyxy.cpu()
        clss = tracks[0].boxes.cls.cpu().tolist()
        trk_ids = tracks[0].boxes.id.int().cpu().tolist()
        annotator = Annotator(im0, line_width=self.tf)
        annotator.draw_region(reg_pts=self.reg_pts, color=(255, 0, 255), thickness=self.tf * 2)

        for box, trk_id, cls in zip(boxes, trk_ids, clss):
            track = self.trk_history[track_id]
            bbox_center = (float((box[0] + box[2]) / 2), float((box[1] + box[3]) / 2))
            track.append(bbox_center)

            if len(track) > 30:
                track.pop(0)

            trk_pts = np.hstack(track).astype(np.int32).reshape((-1, 1, 2))

            if trk_id not in self.trk_pt:
                self.trk_pt[trk_id] = 0

            speed_label = f"{int(self.spd[trk_id])} km/h" if track_id in self.spd else self.names[int(cls)]
            bbox_color = colors(int(trk_id)) if trk_id in self.spd else (255, 0, 255)

            annotator.box_label(box, speed_label, bbox_color)
            cv2.polylines(im0, [trk_pts], isClosed=False, color=(0, 255, 0), thickness=self.tf)
            cv2.circle(im0, (int(track[-1][0]), int(track[-1][1])), self.tf*2, bbox_color, -1)
            self.calculate_speed(trk_id, track)

        if self.view_img and self.env_check:
            cv2.imshow("Ultralytics Speed Estimation", im0)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                return

        return im0


if __name__ == "__main__":
    names = {0: "person", 1: "car"}  # example class names
    speed_estimator = SpeedEstimator(names)
