import os
import json
import pickle
import zipfile
import numpy as np
import pandas as pd
from contextlib import AbstractContextManager
from os.path import abspath
from pathlib import Path

from tracklab.datastruct.tracking_dataset import TrackingSet
from tracklab.utils.coordinates import generate_bbox_from_keypoints, ltrb_to_ltwh

import logging

log = logging.getLogger(__name__)


class TrackerState(AbstractContextManager):
    def __init__(
            self,
            tracking_set: TrackingSet,
            load_file=None,
            json_file=None,  # TODO merge with above behavior
            save_file=None,
            load_from_groundtruth=False,
            compression=zipfile.ZIP_STORED,
            bbox_format=None,
            modules=None,
    ):
        modules = modules or {}
        self.video_metadatas = tracking_set.video_metadatas
        self.image_metadatas = tracking_set.image_metadatas
        self.detections_gt = tracking_set.detections_gt
        self.detections_pred = None

        self.load_file = Path(load_file) if load_file else None
        self.save_file = Path(save_file) if save_file else None
        if self.save_file is not None:
            log.info(f"Saving TrackerState to {abspath(self.save_file)}")
        self.compression = compression
        if self.load_file:
            with zipfile.ZipFile(self.load_file) as zf:
                if "summary.json" in zf.namelist():
                    with zf.open("summary.json") as fp:
                        summary = json.load(fp)
                        load_columns = set(summary["columns"])
                else:
                    with zf.open(zf.namelist()[0]) as fp:
                        dets = pickle.load(fp)
                        load_columns = set(dets.columns)
        else:
            load_columns = set()
        self.input_columns = set()
        self.output_columns = set()
        self.forget_columns = []
        for module in modules:
            self.input_columns |= (set(module.input_columns) - self.output_columns)
            self.output_columns |= set(module.output_columns)
            self.forget_columns += getattr(module, "forget_columns", [])

        self.load_columns = list((load_columns - self.output_columns)
                                 | self.input_columns
                                 | {"image_id", "video_id"})
        if self.load_file:
            log.info(f"Loading {self.load_columns} from {self.load_file}")
        self.zf = None
        self.video_id = None
        self.bbox_format = bbox_format

        self.json_file = json_file
        if self.json_file is not None:
            self.load_detections_pred_from_json(json_file)

        self.load_from_groundtruth = load_from_groundtruth
        if self.load_from_groundtruth:
            self.load_groundtruth(self.load_columns)

    def load_groundtruth(self, load_columns):
        # FIXME only work for topdown -> handle bottomup
        # We consider here that detect_multi detects the bbox
        # and that detect_single detects the keypoints
        self.detections_pred = self.detections_gt.copy()[load_columns]

    def load_detections_pred_from_json(self, json_file):
        anns_path = Path(json_file)
        anns_files_list = list(anns_path.glob("*.json"))
        assert len(anns_files_list) > 0, "No annotations files found in {}".format(
            anns_path
        )
        detections_pred = []
        for path in anns_files_list:
            with open(path) as json_file:
                data_dict = json.load(json_file)
                detections_pred.extend(data_dict["annotations"])
        detections_pred = pd.DataFrame(detections_pred)
        detections_pred.rename(columns={"bbox": "bbox_ltwh"}, inplace=True)
        detections_pred.bbox_ltwh = detections_pred.bbox_ltwh.apply(
            lambda x: np.array(x)
        )
        detections_pred["id"] = detections_pred.index
        detections_pred.rename(columns={"keypoints": "keypoints_xyc"}, inplace=True)
        detections_pred.keypoints_xyc = detections_pred.keypoints_xyc.apply(
            lambda x: np.reshape(np.array(x), (-1, 3))
        )
        if self.bbox_format == "ltrb":
            # TODO tracklets coming from Tracktor++ are in ltbr format
            detections_pred.loc[
                detections_pred["bbox_ltwh"].notna(), "bbox_ltwh"
            ] = detections_pred[detections_pred["bbox_ltwh"].notna()].bbox_ltwh.apply(
                lambda x: ltrb_to_ltwh(x)
            )
        detections_pred.loc[
            detections_pred["bbox_ltwh"].isna(), "bbox_ltwh"
        ] = detections_pred[detections_pred["bbox_ltwh"].isna()].keypoints_xyc.apply(
            lambda x: generate_bbox_from_keypoints(x, [0.0, 0.0, 0.0])
        )
        detections_pred["bbox_conf"] = detections_pred.keypoints_xyc.apply(
            lambda x: x[:, 2].mean()
        )
        if detections_pred["bbox_conf"].sum() == 0:
            detections_pred["bbox_conf"] = detections_pred.scores.apply(
                lambda x: x.mean()
            )
            # FIXME confidence score in detections_pred.keypoints_xyc is always 0
        detections_pred = detections_pred.merge(
            self.image_metadatas[["video_id"]],
            how="left",
            left_on="image_id",
            right_index=True,
        )
        self.json_detections_pred = pd.DataFrame(detections_pred)
        if self.do_tracking:
            self.json_detections_pred.drop(
                ["track_id"], axis=1, inplace=True
            )  # TODO NEED TO DROP track_id if we want to perform tracking
        else:
            self.json_detections_pred["track_bbox_kf_ltwh"] = self.json_detections_pred[
                "bbox_ltwh"
            ]  # FIXME config to decide if track_bbox_kf_ltwh or bbox_ltwh should be used

    def __call__(self, video_id):
        self.video_id = video_id
        return self

    def __enter__(self):
        self.zf = {}
        if self.load_file is None:
            load_zf = None
        else:
            load_zf = zipfile.ZipFile(
                self.load_file,
                mode="r",
                compression=self.compression,
                allowZip64=True,
            )

        if self.save_file is None:
            save_zf = None
        else:
            os.makedirs(os.path.dirname(self.save_file), exist_ok=True)
            save_zf = zipfile.ZipFile(
                self.save_file,
                mode="a",
                compression=self.compression,
                allowZip64=True,
            )

        if (self.load_file is not None) and (self.load_file == self.save_file):
            # Fix possible bugs when loading and saving from same file
            zf = zipfile.ZipFile(
                self.load_file,
                mode="a",
                compression=self.compression,
                allowZip64=True,
            )
            self.zf = dict(load=zf, save=zf)
        else:
            self.zf = dict(load=load_zf, save=save_zf)
        return super().__enter__()

    def on_video_loop_end(
            self,
            engine: "TrackingEngine",
            video_metadata: pd.Series,
            video_idx: int,
            detections: pd.DataFrame,
    ):
        self.update(detections)
        self.save()

    def update(self, detections: pd.DataFrame):
        if self.detections_pred is None:
            self.detections_pred = detections
        else:
            self.detections_pred = self.detections_pred[
                ~(self.detections_pred["video_id"] == self.video_id)
            ]
            self.detections_pred = pd.concat(
                [self.detections_pred, detections]
            )  # TODO UPDATE should update existing rows or append if new rows

    def save(self):
        """
        Saves a pickle in a zip file if the video_id is not yet stored in it.
        """
        if self.save_file is None:
            return
        assert self.video_id is not None, "Save can only be called in a contextmanager"
        assert (
                self.detections_pred is not None
        ), "The detections_pred should not be empty when saving"
        if f"{self.video_id}.pkl" not in self.zf["save"].namelist():
            if "summary.json" not in self.zf["save"].namelist():
                with self.zf["save"].open("summary.json", "w") as fp:
                    summary = {"columns": list(self.detections_pred.columns)}
                    summary_bytes = json.dumps(summary, ensure_ascii=False, indent=4).encode(
                        'utf-8')
                    fp.write(summary_bytes)
            with self.zf["save"].open(f"{self.video_id}.pkl", "w") as fp:
                detections_pred = self.detections_pred[
                    self.detections_pred.video_id == self.video_id
                    ]
                pickle.dump(detections_pred, fp, protocol=pickle.DEFAULT_PROTOCOL)
        else:
            log.info(f"{self.video_id} already exists in {self.save_file} file")

    def load(self):
        """
        Returns:
            bool: True if the pickle contains the video detections,
                and False otherwise.
        """
        assert self.video_id is not None, "Load can only be called in a contextmanager"
        if self.json_file is not None:
            return self.json_detections_pred[
                self.json_detections_pred.video_id == self.video_id
                ]
        if self.load_from_groundtruth:
            return self.detections_pred[self.detections_pred.video_id == self.video_id]
        if self.load_file is None:
            return pd.DataFrame()

        if f"{self.video_id}.pkl" in self.zf["load"].namelist():
            with self.zf["load"].open(f"{self.video_id}.pkl", "r") as fp:
                video_detections = pickle.load(fp)
                self.update(video_detections)
                return video_detections[self.load_columns]
        else:
            log.info(f"{self.video_id} not in pklz file")
            return pd.DataFrame()

    def __exit__(self, exc_type, exc_value, traceback):
        """
        TODO : remove all heavy data associated to a video_id
        """
        for zf_type in ["load", "save"]:
            if self.zf[zf_type] is not None:
                self.zf[zf_type].close()
                self.zf[zf_type] = None
        self.video_id = None

        if self.detections_pred is not None:
            self.detections_pred = self.detections_pred.drop(
                columns=self.forget_columns,
                errors="ignore"
            )
