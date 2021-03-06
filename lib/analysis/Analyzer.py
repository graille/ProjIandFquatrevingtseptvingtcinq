# -*- coding: utf-8 -*-
from lib.ImageManager import *


class Analyzer:
    def __init__(self, outpath="out/"):
        self.SAVE_DPI = 850
        self.SAVE_EXTENSION = "png"

        self.outpath = outpath if outpath[-1] == "/" else outpath + "/"

    @staticmethod
    def showKeyPoints(image, keypoints, **kwargs):
        colors = kwargs.get("colors", None)
        if colors:
            for k, keypoint in enumerate(keypoints):
                image = ImageManager.showKeyPoint(image, keypoint,color=colors[k%10])

            return image
        for k, keypoint in enumerate(keypoints):
            image = ImageManager.showKeyPoint(image, keypoint)

        return image

    def saveToFile(self, name):
        plt.savefig(self.outpath + name + "." + self.SAVE_EXTENSION,
                    bbox_inches='tight',
                    format=self.SAVE_EXTENSION,
                    dpi=self.SAVE_DPI)

    def getFunctions(self):
        return []

    def analyze(self):
        # Lancement de l'analyse
        i = 1
        for f in self.getFunctions():
            try:
                i = f(i)
                plt.clf()
                plt.cla()
            except Exception as e:
                print(e.message)
                continue