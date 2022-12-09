from typing import List
from abc import abstractmethod, ABC

from pbtrack.datastruct.detections import Detection, Detections
from pbtrack.datastruct.metadatas import Metadata

class ReIdentifier(ABC):
    """ Abstract class to implement for the integration of a new reidentifier
        in wrapper/reid. The functions to implement are __init__, train 
        (optional), preprocess and process. A description of the expected 
        behavior is provided below.
    """
    @abstractmethod
    def __init__(self, cfg, device):
        """ Init function
        Args:
            cfg (NameSpace): configuration file from Hydra for the reidentifier
            device (str): device to use for the reidentifier        
        """
        self.cfg = cfg
        self.device = device
    
    @abstractmethod
    def preprocess(self, detection: Detection, metadata: Metadata)-> object:
        """ Your pre-processing function to adapt the input to your 
            reidentifier
        Args:
            detection (Detection): the detection to process
            metadata (Metadata): the image metadata associated to the detection
        Returns:
            preprocessed (object): preprocessed input for process()
        """
        pass
        # return pre_processed tel que collate_fn is OK nativement
    
    @abstractmethod
    def process(self, preprocessed_batch, detections: Detections) -> List[Detection]:
        """ Your processing function to run the reidentifier
        Args:
            preprocessed_batch (object): output of preprocess() by batch
            detections (Detections): the detections to update
        Returns:
            detections (List[Detection]): updated detections for the batch
        """
        pass
    
    def train(self):
        """ Training function for your reidentifier
        """
        pass