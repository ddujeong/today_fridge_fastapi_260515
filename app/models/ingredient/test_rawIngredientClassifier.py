import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path
import os
import app.models.ingredient.rawIngredientClassifier as ric
from app.models.ingredient.rawIngredientClassifier import (
    recognize_raw_ingredient_image, 
    RawIngredientCandidate, 
    normalize_label,
    RawIngredientClassifier,
    get_raw_ingredient_classifier
)

class TestRawIngredientClassifier(unittest.TestCase):
    def setUp(self):
        # Reset the singleton before each test
        ric._classifier = None
        # Clear relevant environment variables
        self.env_patcher = patch.dict(os.environ, {}, clear=False)
        self.env_patcher.start()

    def tearDown(self):
        self.env_patcher.stop()

    @patch('app.models.ingredient.rawIngredientClassifier.RawIngredientClassifier')
    def test_recognize_raw_ingredient_image(self, mock_classifier_class):
        # Mock the classifier's recognize method
        mock_instance = MagicMock()
        mock_classifier_class.return_value = mock_instance
        
        # Define a sample output for the recognize method
        sample_output = [
            RawIngredientCandidate(displayName='사과', normalizedName='사과', categorySuggestion='과일', confidence=0.9, bbox=None, modelLabel='apple').to_dict()
        ]
        
        # Set the mock to return this sample output
        mock_instance.recognize.return_value = sample_output
        
        # Call the function with a dummy image path
        result = recognize_raw_ingredient_image(image_path='dummy/path/to/image.jpg', top_k=1)
        
        # Assert that the result matches the expected output
        self.assertEqual(result, sample_output)
        
        # Verify that the classifier was instantiated with the correct DEFAULT parameters
        mock_classifier_class.assert_called_once_with(
            model_path='app/models/ingredient/weights/raw_ingredient_best.pt', 
            confidence_threshold=0.2, 
            device=None, 
            imgsz=224
        )
        mock_instance.recognize.assert_called_once_with(image_path='dummy/path/to/image.jpg', top_k=1)

    @patch('app.models.ingredient.rawIngredientClassifier.RawIngredientClassifier')
    def test_get_raw_ingredient_classifier_env_vars(self, mock_classifier_class):
        # Test if environment variables are correctly picked up
        with patch.dict(os.environ, {
            "RAW_INGREDIENT_MODEL_PATH": "custom/model.pt",
            "RAW_INGREDIENT_CONFIDENCE_THRESHOLD": "0.5",
            "RAW_INGREDIENT_DEVICE": "cpu",
            "RAW_INGREDIENT_IMGSZ": "640"
        }):
            get_raw_ingredient_classifier()
            
            mock_classifier_class.assert_called_once_with(
                model_path="custom/model.pt",
                confidence_threshold=0.5,
                device="cpu",
                imgsz=640
            )

    def test_normalize_label(self):
        # Test cases for normalize_label function
        self.assertEqual(normalize_label('사과'), '사과')
        self.assertEqual(normalize_label('  사과 '), '사과')
        self.assertEqual(normalize_label('사 과'), '사_과')
        self.assertEqual(normalize_label('사-과'), '사_과')
        self.assertEqual(normalize_label('Apple'), 'apple')
        self.assertEqual(normalize_label('Red-Apple'), 'red_apple')
        self.assertEqual(normalize_label('Green Apple'), 'green_apple')
        self.assertEqual(normalize_label(123), '123')

    def test_classifier_init_file_not_found(self):
        # Test that RawIngredientClassifier raises FileNotFoundError if model doesn't exist
        with self.assertRaises(FileNotFoundError):
            RawIngredientClassifier(model_path="non/existent/path.pt")

    @patch('app.models.ingredient.rawIngredientClassifier.Path.exists')
    def test_classifier_init_success_path(self, mock_exists):
        # Mock Path.exists to return True so YOLO init is reached
        mock_exists.return_value = True
        
        # We need to mock YOLO to avoid actually loading it
        with patch('ultralytics.YOLO') as mock_yolo:
            clf = RawIngredientClassifier(model_path="dummy.pt")
            self.assertEqual(clf.model_path, Path("dummy.pt"))
            mock_yolo.assert_called_once_with("dummy.pt")

    @patch('app.models.ingredient.rawIngredientClassifier.Path.exists')
    def test_recognize_empty_results(self, mock_exists):
        mock_exists.return_value = True
        with patch('ultralytics.YOLO') as mock_yolo:
            mock_model = MagicMock()
            mock_yolo.return_value = mock_model
            mock_model.predict.return_value = []
            
            clf = RawIngredientClassifier(model_path="dummy.pt")
            result = clf.recognize("image.jpg")
            self.assertEqual(result, [])

    def test_topk_candidates_mapping(self):
        # Manually test _topk_candidates logic
        with patch('app.models.ingredient.rawIngredientClassifier.Path.exists') as mock_exists:
            mock_exists.return_value = True
            with patch('ultralytics.YOLO'):
                clf = RawIngredientClassifier(model_path="dummy.pt")
                
                # Mock probs and names
                mock_probs = MagicMock()
                mock_probs.data.detach().cpu().tolist.return_value = [0.1, 0.8, 0.1]
                names = {0: "apple", 1: "onion", 2: "unknown_item"}
                
                candidates = clf._topk_candidates(probs=mock_probs, names=names, top_k=2)
                
                # Should be 1 because apple (0.1) is below default threshold (0.2) 
                # and we already have onion (0.8) as a candidate.
                self.assertEqual(len(candidates), 1)
                
                # First should be onion (0.8)
                self.assertEqual(candidates[0].displayName, "양파")
                self.assertEqual(candidates[0].normalizedName, "양파")
                self.assertEqual(candidates[0].categorySuggestion, "채소")
                self.assertEqual(candidates[0].confidence, 0.8)

    def test_topk_candidates_no_mapping(self):
         with patch('app.models.ingredient.rawIngredientClassifier.Path.exists') as mock_exists:
            mock_exists.return_value = True
            with patch('ultralytics.YOLO'):
                clf = RawIngredientClassifier(model_path="dummy.pt", confidence_threshold=0.05)
                
                mock_probs = MagicMock()
                mock_probs.data.detach().cpu().tolist.return_value = [0.1]
                names = {0: "unmapped_label"}
                
                candidates = clf._topk_candidates(probs=mock_probs, names=names, top_k=1)
                self.assertEqual(candidates[0].displayName, "unmapped_label")
                self.assertEqual(candidates[0].normalizedName, "unmapped_label")
                self.assertIsNone(candidates[0].categorySuggestion)

if __name__ == '__main__':
    unittest.main()
