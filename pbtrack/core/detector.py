from typing import List
from abc import abstractmethod, ABC

from pbtrack.datastruct.detections import Detection
from pbtrack.datastruct.metadatas import Metadata, Metadatas

class Detector(ABC):
    """ Abstract class to implement for the integration of a new detector
        in wrapper/detect. The functions to implement are __init__, train 
        (optional), preprocess and process. A description of the expected 
        behavior is provided below.
    """
    @abstractmethod
    def __init__(self, cfg, device):
        """ Init function
        Args:
            cfg (NameSpace): configuration file from Hydra for the detector
            device (str): device to use for the detector
        Attributes:
            id (int): id of the detection
        """
        self.cfg = cfg
        self.device = device
        self.id = 0
    
    @abstractmethod
    def preprocess(self, metadata: Metadata) -> object:
        """ Your preprocessing function to adapt the input to your detector
        Args:
            image (Image): the image metadata to process
        Returns:
            preprocessed (object): preprocessed input for process()
        """
        pass
    
    @abstractmethod
    def process(self, preprocessed_batch, metadatas: Metadatas) -> List[Detection]:
        """ Your processing function to run the detector
        Args:
            preprocessed_batch (object): output of preprocess() by batch
            metadatas (Metadatas): the images metadata associated to the batch
        Returns:
            detections (List[Detection]): list of new detections for the batch
        """
        pass

    def train(self):
        """ Training function for your detector
        """
        pass