import csv
import os
import sys

import cv2
import mediapipe as mp
import numpy as np
import tqdm
from PIL import Image, ImageDraw
from matplotlib import pyplot as plt
from mediapipe.python.solutions import drawing_utils as mp_drawing
from mediapipe.python.solutions import pose as mp_pose
from mediapipe.python.solutions.drawing_utils import DrawingSpec

from matplot_util import show_image, draw_plot_landmarks_save

mp_drawing_styles = mp.solutions.drawing_styles


class BootstrapHelper(object):
    """Helps to bootstrap images and filter pose samples for classification."""

    def __init__(self,
                 difficulty_level,
                 data_set_folder,
                 per_level_out_folder,
                 csvs_out_folder):
        self._images_in_folder = None
        self._images_out_folder = None
        self._csv_out_writer = None

        self._pose_landmarks_3d_dir = os.path.join('pose_landmark_3d_image', difficulty_level)

        self._difficulty_level = difficulty_level
        self._data_set_folder = data_set_folder
        self._per_level_out_folder = per_level_out_folder
        self._csvs_out_folder = csvs_out_folder

        print('#####################################################')
        print('# Bootstrapping level: {}'.format(difficulty_level))
        print('#####################################################')

        # Get list of pose classes and print image statistics.
        self._pose_class_names = sorted(
            [data for data in os.listdir(self._data_set_folder) if not data.startswith('.')])

    def _bootstrap_internal(self, image_name, pose_class_name):
        # Load image.
        input_frame = cv2.imread(os.path.join(self._images_in_folder, image_name))

        # Image Dimension
        image_height, image_width, _ = input_frame.shape

        # Initialize fresh pose tracker and run it.
        with mp_pose.Pose(
                static_image_mode=True,
                enable_segmentation=True,
                model_complexity=1,
                min_detection_confidence=0.7,
        ) as pose_tracker:
            result = pose_tracker.process(cv2.cvtColor(input_frame, cv2.COLOR_BGR2RGB))
            pose_landmarks = result.pose_landmarks

        # Save image with pose prediction (if pose was detected).
        output_frame = input_frame.copy()
        output_frame = cv2.cvtColor(output_frame, cv2.COLOR_RGB2BGR)
        cv2.imwrite(os.path.join(self._images_out_folder, image_name), output_frame)

        # Save landmarks if pose was detected.
        if pose_landmarks is not None:
            # Get landmarks.
            frame_height, frame_width = output_frame.shape[0], output_frame.shape[1]
            pose_landmarks = np.array(
                [[lmk.x * frame_width, lmk.y * frame_height, lmk.z * frame_width]
                 for lmk in pose_landmarks.landmark],
                dtype=np.float32)
            assert pose_landmarks.shape == (33, 3), 'Unexpected landmarks shape: {}'.format(
                pose_landmarks.shape)
            self._csv_out_writer.writerow([image_name] + pose_landmarks.flatten().astype(np.str).tolist())

            annotated_image = input_frame.copy()
            # Draw segmentation on the image.
            # To improve segmentation around boundaries, consider applying a joint
            # bilateral filter to "results.segmentation_mask" with "image".
            condition = np.stack((result.segmentation_mask,) * 3, axis=-1) > 0.1
            bg_image = np.zeros(input_frame.shape, dtype=np.uint8)
            bg_image[:] = (192, 192, 192)
            # annotated_image = np.where(condition, annotated_image, bg_image)
            # Draw pose landmarks on the image.
            mp_drawing.draw_landmarks(
                annotated_image,
                result.pose_landmarks,
                mp_pose.POSE_CONNECTIONS,
                landmark_drawing_spec=DrawingSpec(color=(255, 0, 0), thickness=4))
            cv2.imwrite(os.path.join(self._pose_landmarks_3d_dir, pose_class_name, image_name + '.png'),
                        annotated_image)
            # Uncomment if you want to plot pose world landmarks.
            draw_plot_landmarks_save(
                self._difficulty_level,
                pose_class_name,
                image_name,
                result.pose_world_landmarks,
                mp_pose.POSE_CONNECTIONS,
                landmark_drawing_spec=DrawingSpec(color=(255, 0, 0), thickness=5),
                connection_drawing_spec=DrawingSpec(color=(0, 0, 0), thickness=2)
            )

        # Draw XZ projection and concatenate with the image.
        # projection_xz = self._draw_xz_projection(
        #     output_frame=output_frame, pose_landmarks=pose_landmarks)
        # output_frame = np.concatenate((output_frame, projection_xz), axis=1)
        # show_image(output_frame)

    def bootstrap(self, per_pose_class_limit=None):
        """Bootstraps images in a given folder.

        Required image in [guru_asana_data_sets_in] folder:
            beginner/
              beginner_cobra_pose/
                1.jpg
                2.jpg
                3.jpg
                ...
                N.jpg
            intermediate/
            ...
        similar use for image out folder but:
            difficulty level + pose class name are concatenated
            (i.e., guru_asana_data_sets_out/beginner/beginner_cobra_pose/1.jpg...)

        Produced CSVs out in [guru_asana_pose_out_csv] folder:
          beginner/
            beginner_cobra_pose.csv
            ...
         ...

        Produced CSV structure with pose 3D landmarks:
          1,x1,y1,z1,x2,y2,z2,....
          2,x1,y1,z1,x2,y2,z2,....
        """
        # Create output folder for CVSs.
        if not os.path.exists(self._csvs_out_folder):
            os.makedirs(self._csvs_out_folder)

        for pose_class_name in self._pose_class_names:
            print('Bootstrapping: ', pose_class_name, file=sys.stderr)

            # Create Directory for Pose Landmarks image + 3d world plot per class name inside.
            per_class_name_landmarks_dir = os.path.join(self._pose_landmarks_3d_dir, pose_class_name)
            if not os.path.exists(per_class_name_landmarks_dir):
                os.makedirs(per_class_name_landmarks_dir)

            # Paths for the pose class.
            images_in_folder = os.path.join(self._data_set_folder, pose_class_name)
            images_out_folder = os.path.join(self._per_level_out_folder, pose_class_name)
            csv_out_path = os.path.join(self._csvs_out_folder, pose_class_name + '.csv')
            if not os.path.exists(images_out_folder):
                os.makedirs(images_out_folder)

            with open(csv_out_path, 'w', newline='') as csv_out_file:
                csv_out_writer = csv.writer(csv_out_file, delimiter=',', quoting=csv.QUOTE_MINIMAL)
                # Get list of images.
                image_names = sorted([n for n in os.listdir(images_in_folder) if not n.startswith('.')])
                if per_pose_class_limit is not None:
                    image_names = image_names[:per_pose_class_limit]

                self._images_in_folder = images_in_folder
                self._images_out_folder = images_out_folder
                self._csv_out_writer = csv_out_writer

                # Bootstrap every image.
                for image_name in tqdm.tqdm(image_names):
                    self._bootstrap_internal(image_name, pose_class_name)

    def _draw_xz_projection(self, output_frame, pose_landmarks, r=0.5, color='red'):
        frame_height, frame_width = output_frame.shape[0], output_frame.shape[1]
        img = Image.new('RGB', (frame_width, frame_height), color='white')

        if pose_landmarks is None:
            return np.asarray(img)

        # Scale radius according to the image width.
        r *= frame_width * 0.01

        draw = ImageDraw.Draw(img)
        for idx_1, idx_2 in mp_pose.POSE_CONNECTIONS:
            # Flip Z and move hips center to the center of the image.
            x1, y1, z1 = pose_landmarks[idx_1] * [1, 1, -1] + [0, 0, frame_height * 0.5]
            x2, y2, z2 = pose_landmarks[idx_2] * [1, 1, -1] + [0, 0, frame_height * 0.5]

            draw.ellipse([x1 - r, z1 - r, x1 + r, z1 + r], fill=color)
            draw.ellipse([x2 - r, z2 - r, x2 + r, z2 + r], fill=color)
            draw.line([x1, z1, x2, z2], width=int(r), fill=color)

        return np.asarray(img)

    def align_images_and_csvs(self, print_removed_items=False, difficulty_level=None):
        """Makes sure that image folders and CSVs have the same sample.

        Leaves only intersection of samples in both image folders and CSVs.
        """
        for pose_class_name in self._pose_class_names:
            # Paths for the pose class.
            images_out_folder = os.path.join(self._per_level_out_folder, pose_class_name)
            csv_out_path = os.path.join(self._csvs_out_folder, pose_class_name + '.csv')

            # Read CSV into memory.
            rows = []
            with open(csv_out_path) as csv_out_file:
                csv_out_reader = csv.reader(csv_out_file, delimiter=',')
                for row in csv_out_reader:
                    if not len(row) == 0:
                        rows.append(row)

            # Image names left in CSV.
            image_names_in_csv = []

            # Re-write the CSV removing lines without corresponding images.
            with open(csv_out_path, 'w', newline='') as csv_out_file:
                csv_out_writer = csv.writer(csv_out_file, delimiter=',', quoting=csv.QUOTE_MINIMAL)
                for row in rows:
                    print(row)
                    image_name = row[0]
                    image_path = os.path.join(images_out_folder, image_name)
                    if os.path.exists(image_path):
                        image_names_in_csv.append(image_name)
                        csv_out_writer.writerow(row)
                    elif print_removed_items:
                        print('Removed image from {} CSV: {}'.format(difficulty_level, image_path))

            # Remove images without corresponding line in CSV.
            for image_name in os.listdir(images_out_folder):
                if image_name not in image_names_in_csv:
                    image_path = os.path.join(images_out_folder, image_name)
                    os.remove(image_path)
                    if print_removed_items:
                        print('Removed image from folder: ', image_path)

    def analyze(self, outliers, fig):
        for i in range(1, len(outliers) + 1):
            print(i)
            image_path = os.path.join(self._per_level_out_folder, outliers[i - 1].sample.class_name,
                                      outliers[i - 1].sample.name)
            img = cv2.imread(image_path)
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            axs = fig.add_subplot(5, len(outliers) + 1 / 5, i)
            axs.set_title(outliers[i - 1].sample.name, fontsize=42)
            plt.imshow(img)
        plt.show()

    def analyze_outliers(self, outliers, original_input_folder=None):
        if len(outliers) == 0:
            pass
        print('Analyzing outliers')
        """Classifies each sample against all other to find outliers.

        If sample is classified differently than the original class - it sold
        either be deleted or more similar samples should be added.
        """

        image_path_folder = self._per_level_out_folder

        if original_input_folder is not None:
            image_path_folder = original_input_folder

        for outlier in outliers:
            image_path = os.path.join(image_path_folder, outlier.sample.class_name, outlier.sample.name)

            print('Outlier')
            print('  sample path =    ', image_path)
            print('  sample class =   ', outlier.sample.class_name)
            print('  detected class = ', outlier.detected_class)
            print('  all classes =    ', outlier.all_classes)

            # img = cv2.imread(image_path)
            # img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            # show_image(img, figsize=(20, 20))

    def remove_outliers(self, outliers):
        """Removes outliers from the image folders."""
        print('Removing outliers')
        for outlier in outliers:
            image_path = os.path.join(self._per_level_out_folder, outlier.sample.class_name, outlier.sample.name)
            os.remove(image_path)

    def print_images_in_statistics(self):
        """Prints statistics from the input image folder."""
        self._print_images_statistics(self._data_set_folder)

    def print_images_out_statistics(self):
        """Prints statistics from the output image folder."""
        self._print_images_statistics(self._per_level_out_folder)

    def _print_images_statistics(self, images_folder):
        print('Number of images per pose class:')
        for pose_class_name in self._pose_class_names:
            n_images = len([
                n for n in os.listdir(os.path.join(images_folder, pose_class_name))
                if not n.startswith('.')])
            print('  {}: {}'.format(pose_class_name, n_images))
