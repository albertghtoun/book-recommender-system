import os
import math
from pyspark.mllib.recommendation import ALS
from pyspark.mllib.recommendation import MatrixFactorizationModel
import logging
from subprocess import call

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_counts_and_averages(ID_and_ratings_tuple):
    """Given a tuple (bookID, ratings_iterable) 
    returns (bookID, (ratings_count, ratings_avg))
    """
    nratings = len(ID_and_ratings_tuple[1])
    return ID_and_ratings_tuple[0], (nratings, float(sum(x for x in ID_and_ratings_tuple[1]))/nratings)


class RecommendationEngine:
    """A book recommendation engine
    """

    def __count_and_average_ratings(self):
        """Updates the books ratings counts from 
        the current data self.training_RDD
        """
        logger.info("Counting book ratings...")
        book_ID_with_ratings_RDD = self.training_RDD.map(lambda x: (x[1], x[2])).groupByKey()
        book_ID_with_avg_ratings_RDD = book_ID_with_ratings_RDD.map(get_counts_and_averages)
        self.books_rating_counts_RDD = book_ID_with_avg_ratings_RDD.map(lambda x: (x[0], x[1][0]))


    def __train_model(self):
        """Train the ALS model with the current dataset
        """
        logger.info("Training the ALS model...")
        self.model = ALS.train(self.training_RDD, self.best_rank, seed=self.seed,
                               iterations=self.iterations, lambda_=self.regularization_parameter)
        logger.info("ALS model built!")

    def __test_model(self):
        test_for_predict_RDD = self.test_RDD.map(lambda x: (x[0], x[1]))

        predictions = self.model.predictAll(test_for_predict_RDD).map(lambda r: ((r[0], r[1]), r[2]))
        rates_and_preds = self.test_RDD.map(lambda r: ((int(r[0]), int(r[1])), float(r[2]))).join(predictions)
        error = math.sqrt(rates_and_preds.map(lambda r: (r[1][0] - r[1][1])**2).mean())
    
        print 'For testing data the RMSE is %s' % (error) 

 
    def determine_best_rank(self, ranks):
        best = -1
        min_error = float('inf')
        errors = [0]*len(ranks)
        err = 0
        for rank in ranks:
            model = ALS.train(self.training_RDD, rank, seed=self.seed,
                               iterations=self.iterations, lambda_=self.regularization_parameter)
            predictions = model.predictAll(self.validation_for_predict_RDD).map(lambda r: ((r[0], r[1]), r[2]))
            print predictions.take(5)
            rates_and_preds = self.validation_RDD.map(lambda r: ((int(r[0]), int(r[1])), float(r[2]))).join(predictions)
            print rates_and_preds.take(5)

            error = math.sqrt(rates_and_preds.map(lambda r: (r[1][0] - r[1][1])**2).mean()) 
            errors[err] = error
            err += 1
            print 'The RMSE for rank %d is %s' % (rank, error)
            if error < min_error:
                min_error = error
                best = rank
        
        print 'The best model was trained with rank %s' % best
        return best
 
    def __predict_ratings(self, user_and_book_RDD):
        """Gets predictions for a given (userID, bookID) formatted RDD
        Returns: an RDD with format (bookTitle, bookRating, numRatings)
        """
        predicted_RDD = self.model.predictAll(user_and_book_RDD)
        predicted_rating_RDD = predicted_RDD.map(lambda x: (x.product, x.rating))
        print predicted_rating_RDD.take(5)
        print self.books_titles_RDD.take(5)
        print self.books_rating_counts_RDD.take(5)

        predicted_rating_title_and_count_RDD = \
            predicted_rating_RDD.join(self.books_titles_RDD).join(self.books_rating_counts_RDD)
        print predicted_rating_title_and_count_RDD.take(5)
        predicted_rating_title_and_count_RDD = \
            predicted_rating_title_and_count_RDD.map(lambda r: (r[1][0][1], r[1][0][0], r[1][1]))
        
        return predicted_rating_title_and_count_RDD
    
    def add_ratings(self, ratings):
        """Add additional book ratings in the format (user_id, book_id, rating)
        """
        # Convert ratings to an RDD
        new_ratings_RDD = self.sc.parallelize(ratings)
        # Add new ratings to the training_RDD
        self.training_RDD = self.training_RDD.union(new_ratings_RDD)
        # Add new ratings to the ratings_RDD
        self.ratings_RDD = self.ratings_RDD.union(new_ratings_RDD)
        # Re-compute book ratings count
        self.__count_and_average_ratings()
        # Re-train the ALS model with the new ratings
        self.__train_model()
        
        return ratings

    def get_ratings_for_book_ids(self, user_id, book_ids):
        """Given a user_id and a list of book_ids, predict ratings for them 
        """
        requested_books_RDD = self.sc.parallelize(book_ids).map(lambda x: (user_id, x))
        # Get predicted ratings
        ratings = self.__predict_ratings(requested_books_RDD).collect()

        return ratings
    
    def get_top_ratings(self, user_id, books_count):
        """Recommends up to books_count top unrated books to user_id
        """
        # Get pairs of (userID, bookID) for user_id unrated books
        user_unrated_books_RDD = self.ratings_RDD.filter(lambda rating: not rating[0] == user_id)\
                                                 .map(lambda x: (user_id, x[1])).distinct()
        # Get predicted ratings
        ratings = self.__predict_ratings(user_unrated_books_RDD).filter(lambda r: r[2]>=25).takeOrdered(books_count, key=lambda x: -x[1])

        return ratings

    def load_ratings(self, dataset_path, rating_file, train_validate_test):
        ratings_file_path = os.path.join(dataset_path, rating_file)
        ratings_raw_RDD = self.sc.textFile(ratings_file_path)
        ratings_raw_data_header = ratings_raw_RDD.take(1)[0]
        self.ratings_RDD = ratings_raw_RDD.filter(lambda line: line!=ratings_raw_data_header)\
            .map(lambda line: line.split(";")).map(lambda tokens: (int(tokens[0]),int(tokens[1]),float(tokens[2]))).cache()
        print self.ratings_RDD.take(3)

        #split the dataset into training, validation and testing datasets
        self.training_RDD, self.validation_RDD, self.test_RDD = self.ratings_RDD.randomSplit(train_validate_test, seed=0L)
        print "training_RDD"
        print self.training_RDD.take(3)
        
        self.validation_for_predict_RDD = self.validation_RDD.map(lambda x: (x[0], x[1]))
        print "validation_for_predict_RDD"
        print self.validation_for_predict_RDD.take(3)

        self.test_for_predict_RDD = self.test_RDD.map(lambda x: (x[0], x[1]))        
        print "test_for_predict_RDD"
        print self.test_for_predict_RDD.take(3)
        
    def __init__(self, sc, dataset_path):
        """Init the recommendation engine given a Spark context and a dataset path
        """

        logger.info("Starting up the Recommendation Engine: ")
        self.sc = sc

        self.model_path = os.path.join('models')
        # test if model is exist, if it is, load the model.
        # ret = call(["hadoop", "fs", "-test", "-e", "models"])
    
        ret = 1 
        if ret == 0:   # the model is exist
            print "the model folder exists. just load data and model."
            # Load ratings data for later use
            logger.info("Loading All Ratings data...")
            self.load_ratings(dataset_path, 'book-ratings2.csv', [10, 0, 0])
            # Pre-calculate books ratings counts
            self.__count_and_average_ratings()

            # Load books data
            logger.info("Loading Books data...")
            books_file_path = os.path.join(dataset_path, 'books.csv')
            books_raw_RDD = self.sc.textFile(books_file_path)
            books_raw_data_header = books_raw_RDD.take(1)[0]
            self.books_RDD = books_raw_RDD.filter(lambda line: line!=books_raw_data_header)\
                .map(lambda line: line.split(";")).map(lambda tokens: (int(tokens[0]),tokens[1], tokens[2], tokens[3], tokens[4], tokens[5], tokens[6], tokens[7], tokens[8])).cache()
            self.books_titles_RDD = self.books_RDD.map(lambda x: (int(x[0]),x[1], x[2], x[3])).cache()
            print self.books_RDD.take(3)
            
            self.model = MatrixFactorizationModel.load(sc, self.model_path)
            return

        # Load medium ratings data to determine best_rank
        logger.info("Loading Medium Ratings data...")
        #self.load_ratings(dataset_path, 'book-ratings_small2.csv')
        self.load_ratings(dataset_path, 'book-ratings_medium2.csv', [8, 2, 0])
        #setup the parameters, we will determine the rank later using small dataset
        self.seed = 5L
        self.iterations = 10
        self.regularization_parameter = 0.1
        self.best_rank = self.determine_best_rank([2, 4, 6, 8, 10, 12, 14, 16]) 
        
        # Load ratings data
        logger.info("Loading Large Ratings data...")
        self.load_ratings(dataset_path, 'book-ratings2.csv', [7, 0, 3])
        
        #for itr in [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16]:
        #print "training %d iteration." % (itr)          
        self.iterations = 16
            # Train the model
        self.__train_model()
            # Test the model
        self.__test_model()

        # Load books data
        logger.info("Loading Books data...")
        books_file_path = os.path.join(dataset_path, 'books.csv')
        books_raw_RDD = self.sc.textFile(books_file_path)
        books_raw_data_header = books_raw_RDD.take(1)[0]
        self.books_RDD = books_raw_RDD.filter(lambda line: line!=books_raw_data_header)\
            .map(lambda line: line.split(";")).map(lambda tokens: (int(tokens[0]),tokens[1],tokens[2], tokens[3], tokens[4], tokens[5], tokens[6], tokens[7], tokens[8])).cache()
        self.books_titles_RDD = self.books_RDD.map(lambda x: (int(x[0]),x[1], x[2], x[3])).cache()
        print self.books_RDD.take(3)
 
        # Load ratings data for later use
        logger.info("Loading All Ratings data...")
        self.load_ratings(dataset_path, 'book-ratings2.csv', [10, 0, 0])
        # Pre-calculate books ratings counts
        self.__count_and_average_ratings()

        # Train the largest model
        self.__train_model()
        #self.model.save(sc, self.model_path)
