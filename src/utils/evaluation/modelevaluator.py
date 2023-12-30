# evaluator.py
import torch
from src.utils.logging.loggerfactory import LoggerFactory
import utils.files.pathutils as pathutils
import utils.models.modelfactory as modelfactory
from src.config import config
import utils.metrics.metricutils as metricutils
import utils.files.modelloadingutils as modelloadingutils
from tqdm import tqdm
import numpy as np
import torch.nn as nn
import random
import os
import itertools

# Initialize logger for this module.
logger = LoggerFactory.get_logger(f"logger.{__name__}")

class ModelEvaluator:
    def __init__(self, model, criterion, device, tensorBoardWriter=None, config=config, epochs=None):
        """
        Initializes the ModelEvaluator with a given model, loss criterion, device,
        optional TensorBoard writer, and configuration.

        Parameters:
            model (torch.nn.Module): The model to evaluate.
            criterion (function): The loss function.
            device (torch.device): The device to run evaluation on (CPU or GPU).
            tensorBoardWriter (TensorBoardWriter, optional): Writer for TensorBoard logging.
            config (object): An immutable configuration object with necessary parameters.
        """
        self.model = model
        self.config = config
        self.criterion = criterion
        self.device = device
        self.num_classes = config.num_classes
        self.tensorBoardWriter = tensorBoardWriter
        self.epochs = epochs

    def __enter__(self):
        """
        Context management method to use with 'with' statements.
        """
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """
        Context management method to close the TensorBoard writer upon exiting the 'with' block.
        """
        if self.tensorBoardWriter:
            self.tensorBoardWriter.close_writer()

    @classmethod
    def from_trainer(cls, model_trainer):
        """
        Creates a ModelEvaluator instance from a ModelTrainer instance by extracting
        the relevant attributes.

        Parameters:
            model_trainer (ModelTrainer): The trainer instance to extract attributes from.

        Returns:
            ModelEvaluator: A new instance of ModelEvaluator.
        """
        return cls(
            model=model_trainer.model,
            criterion=model_trainer.criterion,
            device=model_trainer.device,
            config=model_trainer.config,
            tensorBoardWriter=model_trainer.tensorBoardWriter
        )
    
    @classmethod
    def from_file(cls, device, tensorBoardWriter=None, thisconfig=config):
        """
        Creates a ModelEvaluator instance from a model file by loading in the model and preparing it
          to be run.

        Parameters:
            device (torch.device): The device to run evaluation on (CPU or GPU).
            tensorBoardWriter (TensorBoardWriter, optional): Writer for TensorBoard logging.
            config (object): An immutable configuration object with necessary parameters.
        """
        
        thisconfig = config
        model = modelfactory.create_model(
            thisconfig.model_name,
            requires_grad=thisconfig.model_requires_grad,
            num_classes=thisconfig.num_classes,
            weights=thisconfig.model_weights
        ).to(device)
        criterion = nn.BCEWithLogitsLoss()

        modelToLoadPath = pathutils.get_model_to_load_path(thisconfig)
        epochs = 0
        if os.path.exists(modelToLoadPath):
            logger.info("Loading the best model...")    
            _, epochs = modelloadingutils.load_model(modelToLoadPath, model)
        else:
            logger.error(f"Could not find a model at path: {modelToLoadPath}")
            raise ValueError(f"Could not find a model at path: {modelToLoadPath}. Check to ensure the config/json value for model_name_to_load is correct!")
        
        return cls(
            model=model,
            criterion=criterion,
            device=device,
            config=thisconfig,
            tensorBoardWriter=tensorBoardWriter,
            epochs= epochs
        )
        
    def predict(self, data_loader):
        """
        Perform inference on the given data_loader and return raw predictions.

        Parameters:
            data_loader (DataLoader): DataLoader for inference.

        Returns:
            prediction_labels (numpy.ndarray): Raw model outputs.
            true_labels (numpy.ndarray): Corresponding true labels.
        """
        self.model.eval()  # Set the model to evaluation mode
        prediction_labels = []  # List to store all raw model outputs
        true_labels = []  # List to store all labels
        total_loss = 0.0  # Initialize total loss

        with torch.no_grad():  # Disable gradient calculation for efficiency
            for batch in tqdm(data_loader, total=len(data_loader)):
                images, labels = batch['image'].to(self.device), batch['label'].to(self.device)

                outputs = self.model(images)
                loss = self.criterion(outputs, labels.float())  # Calculate loss
                total_loss += loss.item()  # Accumulate loss
                prediction_labels.append(outputs.cpu().numpy())  # Store raw model outputs
                true_labels.append(labels.cpu().numpy())  # Store labels

        # Concatenate all raw outputs and labels from all batches
        prediction_labels = np.vstack(prediction_labels)
        true_labels = np.vstack(true_labels)

        # Calculate average loss
        avg_loss = total_loss / len(data_loader.dataset)

        return prediction_labels, true_labels, avg_loss

    def evaluate_old(self, data_loader, epoch, datasetSubset, metricMode=None, threshold=None):
        """
        Evaluate the model on the given data_loader.

        Parameters:
            data_loader (DataLoader): DataLoader for evaluation.
            epoch (int): The current epoch number, used for TensorBoard logging.
            datasetSubset (str): Indicates the subset of data evaluated (e.g., 'test', 'validation').
            metricMode (str, optional): Indicates the type of metric to log ('binary', 'multiclass', etc.).
            threshold (float, optional): The threshold value for binary predictions.

        Returns:
            avg_loss (float): The average loss over the dataset.
            f1_score (float): The F1 score of the model on the dataset.
        """
        self.model.eval()  # Set the model to evaluation mode
        total_loss = 0.0  # Initialize total loss
        all_preds = []  # List to store all predictions
        all_labels = []  # List to store all labels
        random_batch_index = random.randint(0, len(data_loader) - 1)  # Pick a random batch for TensorBoard logging

        with torch.no_grad():  # Disable gradient calculation for efficiency
            for i, batch in enumerate(tqdm(data_loader, total=len(data_loader))):
                images, labels = batch['image'].to(self.device), batch['label'].to(self.device)
                outputs = self.model(images)
                loss = self.criterion(outputs, labels.float())  # Calculate loss
                total_loss += loss.item()  # Accumulate loss

                predictions = metricutils.getpredictions_with_threshold(outputs, threshold=threshold)
                all_preds.append(predictions.cpu().numpy())  # Store predictions
                all_labels.append(labels.cpu().numpy())  # Store labels

                # Log images with predictions to TensorBoard for a random batch, if configured
                if metricMode is not None and self.tensorBoardWriter is not None and i == random_batch_index:
                    self.tensorBoardWriter.write_image_test_results(images, labels, predictions, epoch, metricMode, datasetSubset)

        # Concatenate all predictions and labels from all batches
        all_preds_binary = np.vstack(all_preds)
        all_labels_binary = np.vstack(all_labels)

        # Calculate F1 score
        f1_score = metricutils.f1_score(all_labels_binary, all_preds_binary)

        # Calculate average loss
        avg_loss = total_loss / len(data_loader.dataset)

        # Return the average loss and F1 score
        return avg_loss, f1_score

    def evaluate_predictions(self, data_loader, prediction_outputs, true_labels, epoch, datasetSubset, average, metricMode=None, threshold=None):
        """
        Evaluate the model on the given data_loader.

        Parameters:
            data_loader (DataLoader): DataLoader for evaluation.
            prediction_outputs (numpy.ndarray): Raw model outputs.
            true_labels (numpy.ndarray): Corresponding true labels.
            epoch (int): The current epoch number, used for TensorBoard logging.
            datasetSubset (str): Indicates the subset of data evaluated (e.g., 'test', 'validation').
            average (str): Indicates the type of averaging to perform when computing metrics. Use None to get per-class metrics.
            metricMode (str, optional): Indicates from where this is being evaluated from (e.g., 'Train', 'Test').
            threshold (float, optional): The threshold value for binary predictions.

        Returns:
            avg_loss (float): The average loss over the dataset.
            f1_score (float): The F1 score of the model on the dataset.
        """

        predictions_binary = metricutils.getpredictions_with_threshold(prediction_outputs, threshold)
        # Compute evaluation metrics
        precision, recall, f1 = metricutils.compute_metrics(true_labels, predictions_binary, threshold=threshold, average=average)

        # Log images with predictions to TensorBoard for a random batch, if configured
        if metricMode is not None and self.tensorBoardWriter is not None:
            random_batch_index = random.randint(0, len(data_loader) - 1)
            batch_dict = next(itertools.islice(data_loader, random_batch_index, None))
            images = batch_dict['image']  # Assuming the device transfer happens elsewhere if needed
            labels = batch_dict['label']
            
            start_index = random_batch_index * data_loader.batch_size
            end_index = min((random_batch_index + 1) * data_loader.batch_size, len(predictions_binary))

            selected_predictions = predictions_binary[start_index:end_index]
            selected_predictions_tensor = torch.tensor(selected_predictions, device=images.device, dtype=torch.float32)
            self.tensorBoardWriter.write_image_test_results(images, labels, selected_predictions_tensor, epoch, metricMode, datasetSubset)

        # Return the average loss and computed metrics
        return f1, precision, recall

    def evaluate(self, data_loader, epoch, datasetSubset, metricMode=None, average='micro', threshold=None):
        """
        Evaluate the model on the given data_loader.

        Parameters:
            data_loader (DataLoader): DataLoader for evaluation.
            epoch (int): The current epoch number, used for TensorBoard logging.
            datasetSubset (str): Indicates the subset of data being evaluated (e.g., 'test', 'validation').
            average (str): Indicates the type of averaging to perform when computing metrics. Use None to get per-class metrics.
            metricMode (str, optional): Indicates from where this is being evaluated from (e.g., 'Train', 'Test').
            threshold (float, optional): The threshold value for binary predictions.

        Returns:
            avg_loss (float): The average loss over the dataset.
            f1_score (float): The F1 score of the model on the dataset.
        """
        # Perform inference and get raw outputs
        all_outputs, all_labels, avg_loss = self.predict(data_loader)

        f1, precision, recall = self.evaluate_predictions(data_loader, all_outputs, all_labels, epoch, datasetSubset, average, metricMode,threshold)

        # Return the average loss and computed metrics
        return avg_loss, f1, precision, recall