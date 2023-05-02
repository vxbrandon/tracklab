from torch.utils.data import Dataset


class EngineDatapipe(Dataset):
    def __init__(self, model, first=False) -> None:
        self.model = model
        self.img_metadatas = None
        self.detections = None
        self.first = first

    def update(self, img_metadatas, detections=None):
        del self.img_metadatas
        del self.detections
        self.img_metadatas = img_metadatas
        self.detections = detections

    def __len__(self):
        if not self.first:
            return len(self.detections)
        else:
            return len(self.img_metadatas)

    def __getitem__(self, idx):
        if not self.first:
            detection = self.detections.iloc[idx]
            metadata = self.img_metadatas.loc[detection.image_id]
            sample = (
                detection.name,
                self.model.preprocess(detection=detection, metadata=metadata),
            )
            return sample
        else:
            sample = (self.img_metadatas.index[idx], self.model.preprocess(self.img_metadatas.iloc[idx]))
            return sample