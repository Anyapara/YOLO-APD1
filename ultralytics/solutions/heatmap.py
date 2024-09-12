# Ultralytics YOLO 🚀, AGPL-3.0 license

from collections import defaultdict

import cv2
import numpy as np

from ultralytics.utils.checks import check_imshow, check_requirements
from ultralytics.utils.plotting import Annotator

check_requirements("shapely>=2.0.0")

from shapely.geometry import LineString, Point, Polygon


class Heatmap:
    """A class to draw heatmaps in real-time video stream based on their tracks."""

    def __init__(
        self,
        names,
        colormap=cv2.COLORMAP_JET,
        heatmap_alpha=0.5,
        view_img=False,
        count_reg_pts=None,
        line_thickness=2,
        decay_factor=0.99,
    ):
        """Initializes the heatmap class with default values for Visual, Image, track, count and heatmap parameters."""
        # Visual information
        self.annotator = None
        self.view_img = view_img

        self.initialized = False
        self.names = names  # Classes names

        # Image information
        self.im0 = None
        self.tf = line_thickness

        # Heatmap colormap and heatmap np array
        self.colormap = colormap
        self.heatmap = None
        self.heatmap_alpha = heatmap_alpha

        # track information
        self.track_history = defaultdict(list)

        # Region & Line Information
        self.counting_region = None

        # Object Counting Information
        self.in_counts = 0
        self.out_counts = 0
        self.count_ids = []
        self.class_wise_count = {}

        # Decay factor
        self.decay_factor = decay_factor

        # Check if environment supports imshow
        self.env_check = check_imshow(warn=True)

        self.counting_line_segment = None   # Initialize the counting line segment

        # Region and line selection
        self.count_reg_pts = count_reg_pts
        if self.count_reg_pts is not None:
            if len(self.count_reg_pts) == 2:
                print("Line Counter Initiated.")
                self.counting_region = LineString(self.count_reg_pts)
                # Define the counting line segment
                self.counting_line_segment = LineString(
                    [
                        (self.count_reg_pts[0][0], self.count_reg_pts[0][1]),
                        (self.count_reg_pts[1][0], self.count_reg_pts[1][1]),
                    ]
                )
            elif len(self.count_reg_pts) >= 3:
                print("Polygon Counter Initiated.")
                self.counting_region = Polygon(self.count_reg_pts)
            else:
                print("Invalid Region points provided, region_points must be 2 for lines or >= 3 for polygons.")
                print("Using Line Counter Now")
                self.counting_region = LineString(self.count_reg_pts)

    def generate_heatmap(self, im0, tracks):
        """
        Generate heatmap based on tracking data.

        Args:
            im0 (nd array): Image
            tracks (list): List of tracks obtained from the object tracking process.
        """
        self.im0 = im0

        # Initialize heatmap only once
        if not self.initialized:
            self.heatmap = np.zeros((int(self.im0.shape[0]), int(self.im0.shape[1])), dtype=np.float32)
            self.initialized = True

        self.heatmap *= self.decay_factor  # decay factor
        boxes, clss, track_ids = None, None, None
        if tracks[0].boxes.id is not None:
            boxes = tracks[0].boxes.xyxy.cpu()
            clss = tracks[0].boxes.cls.tolist()
            track_ids = tracks[0].boxes.id.int().tolist()

        self.annotator = Annotator(self.im0, self.tf, None)

        if track_ids:
            # Draw counting region
            if self.count_reg_pts is not None:
                self.annotator.draw_region(
                    reg_pts=self.count_reg_pts, color=(255, 0, 255), thickness=self.tf*2
                )

            for box, cls, track_id in zip(boxes, clss, track_ids):
                # Store class info
                if self.names[cls] not in self.class_wise_count:
                    self.class_wise_count[self.names[cls]] = {"IN": 0, "OUT": 0}

                center = (int((box[0] + box[2]) // 2), int((box[1] + box[3]) // 2))
                radius = min(int(box[2]) - int(box[0]), int(box[3]) - int(box[1])) // 2

                y, x = np.ogrid[0 : self.heatmap.shape[0], 0 : self.heatmap.shape[1]]
                mask = (x - center[0]) ** 2 + (y - center[1]) ** 2 <= radius**2

                self.heatmap[int(box[1]) : int(box[3]), int(box[0]) : int(box[2])] += (
                    2 * mask[int(box[1]) : int(box[3]), int(box[0]) : int(box[2])]
                )

                # Store tracking hist
                track_line = self.track_history[track_id]
                track_line.append((float((box[0] + box[2]) / 2), float((box[1] + box[3]) / 2)))
                if len(track_line) > 30:
                    track_line.pop(0)

                prev_position = self.track_history[track_id][-2] if len(self.track_history[track_id]) > 1 else None

                if self.count_reg_pts is not None:
                    # Count objects in any polygon
                    if len(self.count_reg_pts) >= 3:
                        is_inside = self.counting_region.contains(Point(track_line[-1]))

                        if prev_position is not None and is_inside and track_id not in self.count_ids:
                            self.count_ids.append(track_id)

                            if (box[0] - prev_position[0]) * (self.counting_region.centroid.x - prev_position[0]) > 0:
                                self.in_counts += 1
                                self.class_wise_count[self.names[cls]]["IN"] += 1
                            else:
                                self.out_counts += 1
                                self.class_wise_count[self.names[cls]]["OUT"] += 1

                    # Count objects using line
                    elif len(self.count_reg_pts) == 2:
                        if prev_position is not None and track_id not in self.count_ids:
                            # Check if the object's movement segment intersects the counting line
                            if LineString([(prev_position[0], prev_position[1]), (box[0], box[1])]).intersects(
                                    self.counting_line_segment
                            ):
                                self.count_ids.append(track_id)

                                # Determine the direction of movement (IN or OUT)
                                direction = (box[0] - prev_position[0]) * (
                                        self.counting_region.centroid.x - prev_position[0]
                                )
                                if direction > 0:
                                    self.in_counts += 1
                                    self.class_wise_count[self.names[cls]]["IN"] += 1
                                else:
                                    self.out_counts += 1
                                    self.class_wise_count[self.names[cls]]["OUT"] += 1

        else:
            for box, cls in zip(boxes, clss):
                center = (int((box[0] + box[2]) // 2), int((box[1] + box[3]) // 2))
                radius = min(int(box[2]) - int(box[0]), int(box[3]) - int(box[1])) // 2

                y, x = np.ogrid[0 : self.heatmap.shape[0], 0 : self.heatmap.shape[1]]
                mask = (x - center[0]) ** 2 + (y - center[1]) ** 2 <= radius**2

                self.heatmap[int(box[1]) : int(box[3]), int(box[0]) : int(box[2])] += (
                    2 * mask[int(box[1]) : int(box[3]), int(box[0]) : int(box[2])]
                )

        if self.count_reg_pts is not None:
            labels_dict = {}

            for key, value in self.class_wise_count.items():
                labels_dict[str.capitalize(key)] = f"IN {value['IN']} OUT {value['OUT']}"

            if labels_dict is not None:
                self.annotator.display_analytics(self.im0, labels_dict, (104, 31, 17), (255, 255, 255), 10)

        # Normalize, apply colormap to heatmap and combine with original image
        heatmap_normalized = cv2.normalize(self.heatmap, None, 0, 255, cv2.NORM_MINMAX)
        heatmap_colored = cv2.applyColorMap(heatmap_normalized.astype(np.uint8), self.colormap)
        self.im0 = cv2.addWeighted(self.im0, 1 - self.heatmap_alpha, heatmap_colored, self.heatmap_alpha, 0)

        if self.env_check and self.view_img:
            cv2.imshow("Ultralytics Heatmap", self.im0)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                return

        return self.im0


if __name__ == "__main__":
    classes_names = {0: "person", 1: "car"}  # example class names
    heatmap = Heatmap(classes_names)
