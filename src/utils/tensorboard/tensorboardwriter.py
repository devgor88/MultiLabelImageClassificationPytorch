from src.config import config
from torch.utils.tensorboard import SummaryWriter
import src.utils.files.pathutils as pathutils
import src.utils.files.imageutils as imageutils
import src.utils.dataset.datasetutils as datasetutils

class TensorBoardWriter():
    """
    Initializes the TensorBoardWriter with a given configuration.

    Parameters:
        config (module): Configuration module with necessary attributes.
    """
    def __init__(self, config=config):
        self.config = config
        log_dir = pathutils.combine_path(
            pathutils.get_tensorboard_log_dir_path(),
            f'{config.model_name}_{config.model_weights}_{config.image_size}'
        )
        self.writer = SummaryWriter(log_dir)

    def add_scalar(self, tag, scalar_value, step):
        """
        Writes a scalar value to TensorBoard.

        Parameters:
            tag (str): The tag associated with the scalar.
            scalar_value (float): The scalar value to write.
            step (int): The global step value to record.
        """
        self.writer.add_scalar(tag, scalar_value, step)

    def write_image_test_results(self, images, true_labels, predictions, step, runmode, dataSubset):
        """
        Writes image test results with overlays to TensorBoard.

        Parameters:
            images (Tensor): Batch of images.
            true_labels (Tensor): True labels for the images.
            predictions (Tensor): Predicted labels for the images.
            step (int): The global step value to record.
            runmode (str): The mode of the run (e.g., 'Train', 'Test').
            data_subset (str): The subset of data (e.g., 'Validation').
        """
        denormalized_images = imageutils.denormalize_images(images, self.config)
        pil_images = imageutils.convert_to_PIL(denormalized_images)
        overlaid_images = imageutils.overlay_predictions_batch(pil_images, predictions.cpu().tolist(), datasetutils.get_dataset_tag_mappings(self.config), true_labels.cpu().tolist())
        tensor_overlaid_images = imageutils.convert_PIL_to_tensors(overlaid_images)
        self.add_images(f'{runmode}/{dataSubset}/Images', denormalized_images, step)
        self.add_images(f'{runmode}/{dataSubset}/True Labels', imageutils.convert_labels_to_color(true_labels.cpu(), self.config.num_classes), step)
        self.add_images(f'{runmode}/{dataSubset}/Predictions', imageutils.convert_labels_to_color(predictions.cpu(), self.config.num_classes), step)
        self.add_images(f'{runmode}/{dataSubset}/OverlayPredictions', tensor_overlaid_images, step)

    def add_histogram(self, tag, param, step):
        """
        Writes a histogram of values to TensorBoard.

        Parameters:
            tag (str): The tag associated with the histogram.
            values (Tensor): Values to create a histogram.
            step (int): The global step value to record.
        """
        self.writer.add_histogram(tag, param, step)

    def add_images(self, tag, images, step):
        """
        Writes a batch of images to TensorBoard.

        Parameters:
            tag (str): The tag associated with the images.
            images (Tensor): Batch of images to write.
            step (int): The global step value to record.
        """
        self.writer.add_images(tag, images, step)

    def close_writer(self):
        """
        Closes the TensorBoard writer and cleans up resources.
        """
        if self.writer:
            self.writer.close()
            self.writer = None

    def add_hparams(self, hparams, metrics):
        """
        Writes hyperparameters and their associated metrics to TensorBoard.

        Parameters:
            hparams (dict): Dictionary of hyperparameters.
            metrics (dict): Dictionary of metrics associated with the hyperparameters.
        """
        self.writer.add_hparams(hparam_dict=hparams, metric_dict=metrics)