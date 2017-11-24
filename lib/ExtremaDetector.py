# -*- coding: utf-8 -*-
import copy

from lib.ImageManager import *
from lib.analysis.OctaveAnalyzer import *
from lib.analysis.Utils import *


class ExtremaDetector:
    def __init__(self):
        pass

    @staticmethod
    def differenceDeGaussienne(image, s, nb_octave, **kwargs):
        """
        Génère la pyramide des DoGs d'une image
        :param image:       L'image originale
        :param s:           Le facteur s
        :param nb_octave:   Le nombre d'octave à générer
        :return:            (DoGs, pyramide des octaves, liste des sigmas)
        """
        if image is None:
            raise Exception("Erreur : Aucune image envoyee")

        nb_element = s + 3
        verbose = kwargs.get('verbose', False)

        # Construction de la pyramide de gaussiennes
        Log.debug("Génération de la pyramide de Gaussiennes", 1)
        sigmas = [1.6 * (2 ** (float(k) / float(s))) for k in range(nb_element)]
        pyramid = [[] for k in range(nb_octave)]

        for octave in range(nb_octave):
            if octave == 0:
                octave_original = image
            else:
                #  On prend la s + 1 eme image (la numéro s dans le tableau)
                octave_original = ImageManager.divideSizeBy2(pyramid[octave - 1][s])

            for k in range(nb_element):
                pyramid[octave].append(ImageManager.applyGaussianFilter(octave_original, sigmas[k]))

        # Generation de la pyramide des différences
        Log.debug("Génération de la pyramide des différences de Gaussiennes", 1)
        doG = [[] for k in range(nb_octave)]

        for octave in range(nb_octave):
            for k in range(nb_element - 1):
                doG[octave].append(ImageManager.makeDifference(pyramid[octave][k + 1], pyramid[octave][k]))

        return doG, pyramid, sigmas

    @staticmethod
    def detectionPointsCles(DoGs, octaves, sigmas, seuil_contraste, r_courb_principale, resolution_octave, octave_nb,
                            **kwargs):
        """
        Detecte les points clés d'une image
        :param DoGs:                Liste des DoGs pour une octave
        :param octaves:             Liste des images d'une octave
        :param sigmas:              Liste des sigmas (provenant de la convolution par une gaussienne)
        :param seuil_contraste:     Seuil de contraste
        :param r_courb_principale:  Rayon de courbure principal
        :param resolution_octave:   Résolution de l'octave
        :param octave_nb:           Numéro de l'octave
        :return:                    Liste des points clés
        """

        # Quelques vérifications d'usages afin de garantir le bon déroulement de la méthode
        if len(DoGs) == 0:
            raise ("Erreur : Aucune image DoGs fournie en parametre")

        if len(DoGs) < 3:
            raise ("Erreur : Pas assez d'images DoGs fournies en paramètre (3 minimum)")

        # Execution
        height, width = ImageManager.getDimensions(DoGs[0])

        # Génération des DoGs normalisés (valeur en 0 et 1)
        DoGsNormalized = []
        for DoG in DoGs:
            DoGsNormalized.append(ImageManager.normalizeImage(DoG))

        def _filtrerPointsContraste():
            Log.debug("Demarrage du filtrage par contraste", 1)
            realPoints = []

            for i_sigma in range(1, len(DoGs) - 1):
                # On fait une boucle sur l'ensemble des pixels, bords exclus afin de ne pas avoir a faire du cas par cas
                Log.debug("Traitement du sigma " + str(i_sigma) + " : " + str(sigmas[i_sigma]), 2)
                for x in range(1, height - 1):
                    for y in range(1, width - 1):
                        if abs(DoGsNormalized[i_sigma][x, y]) > seuil_contraste:
                            realPoints.append((x, y, i_sigma))

            return realPoints

        def _detectionExtremums(candidats):
            Log.debug("Demarrage de la détéction des extremums", 1)
            extremums = []

            for c in candidats:
                (x, y, i_sigma) = c
                neighbours = []

                neighbours += [DoGs[i_sigma - 1][x - 1:x + 2, y - 1:y + 2]]
                neighbours += [DoGs[i_sigma][x - 1:x + 2, y - 1:y + 2]]
                neighbours += [DoGs[i_sigma + 1][x - 1:x + 2, y - 1:y + 2]]

                neighbours = np.array(neighbours).flat

                # Si le point est effectivement le maximum de la region, c'est un point candidat
                if DoGs[i_sigma][x, y] == np.max(neighbours) or DoGs[i_sigma][x, y] == np.min(neighbours):
                    extremums.append(c)

            return extremums

        def _filtrerPointsArete(candidats):
            Log.debug("Demarrage du filtrage des arêtes", 1)
            realPoints = []

            Dx, Dy, Dxx, Dyy, Dxy = {}, {}, {}, {}, {}

            Fy = np.matrix('-1 0 1;-2 0 2;-1 0 1')
            Fx = np.matrix('1 2 1;0 0 0;-1 -2 -1')

            for k in range(1, len(DoGs) - 1):
                Dx[k] = Filter.convolve2D(DoGsNormalized[k], Fx)
                Dy[k] = Filter.convolve2D(DoGsNormalized[k], Fy)

            for k in range(1, len(DoGs) - 1):
                Dxx[k] = Filter.convolve2D(Dx[k], Fx)
                Dyy[k] = Filter.convolve2D(Dy[k], Fy)
                Dxy[k] = (Filter.convolve2D(Dx[k], Fy) + Filter.convolve2D(Dy[k], Fx)) / 2

            # On calcul la Hessienne
            for c in candidats:
                (x, y, i_sigma) = c

                Tr = Dxx[i_sigma][x, y] + Dyy[i_sigma][x, y]
                Det = (Dxx[i_sigma][x, y] * Dyy[i_sigma][x, y]) - (Dxy[i_sigma][x, y] ** 2)

                R = (Tr ** 2) / Det

                rapport = ((r_courb_principale + 1) ** 2) / r_courb_principale
                if R < rapport:
                    realPoints.append(c)

            return realPoints

        def _assignOrientation(candidats):
            Log.debug("Demarrage de l'assignation d'orientation", 1)
            realPoints = []
            # On creer le slice de l'histogramme
            H_slice = np.linspace(0, 2 * np.pi, 36 + 1)  # 37 valeurs, donc 36 intervalles

            for c in candidats:
                (x, y, i_sigma) = c

                # Pour n, on va chercher dans un voisinage de x-n:x+n, y-n:y+n pixels soit (n+1)**2 pixels
                taille_voisinage = int(sigmas[i_sigma] * 3)
                H = np.zeros(36)

                # Selection des points du voisinage en faisant attention aux bords
                xMax, yMax, xMin, yMin = min(height - 1, x + taille_voisinage), \
                                         min(width - 1, y + taille_voisinage), \
                                         max(1, x - taille_voisinage), \
                                         max(1, y - taille_voisinage)

                g, d, b, h = octaves[i_sigma][(xMin - 1):(xMax - 1), yMin:yMax], \
                             octaves[i_sigma][(xMin + 1):(xMax + 1), yMin:yMax], \
                             octaves[i_sigma][xMin:xMax, (yMin - 1):(yMax - 1)], \
                             octaves[i_sigma][xMin:xMax, (yMin + 1):(yMax + 1)]

                g1, g2 = d - g, b - h

                # TODO : Fenètre gausienne

                # Calcul des amplitude des gradients et de l'orientation
                M = np.sqrt(np.power(g1, 2) + np.power(g2, 2))
                A = np.arctan2(g1, g2)  # On utilise atan2 comme spécifié dans l'article en anglais
                A = (A + 2 * np.pi) % (2 * np.pi)  # Opération permettant de revenir dans l'interval [0:2pi]

                # Analyse des résultats, on aplatit le carré de matrice pour pouvoir lister les angles
                Ms, As = M.flat, A.flat

                for k, angle in enumerate(As):
                    for si in range(36):
                        if angle <= H_slice[si + 1]:
                            H[si] += Ms[k]
                            break

                # On selectionne les angles ayant plus de 80% de la valeur maximale
                mH, angles = np.max(H), []
                for k, a in enumerate(H):
                    if H[k] / mH >= 0.80:
                        angles.append(H_slice[k + 1])

                for a in angles:
                    realPoints.append((x, y, i_sigma, a))

            return realPoints

        # On initialise la tableau d'analyse pour l'analyseur
        pyramid_analyzer = kwargs.get("pyramid_analyzer", None)
        analyseur = OctaveAnalyzer(octave_nb, width, height) if pyramid_analyzer else None
        elements = {} if analyseur else None

        # Filtrage des points de faible contrastes
        candidats = _filtrerPointsContraste()
        Log.debug(str(len(candidats)) + " points", 1)
        if analyseur:
            elements["kp_after_contrast_limitation"] = copy.deepcopy(candidats)

        # Detection des extremums
        candidats = _detectionExtremums(candidats)
        if analyseur:
            elements["kp_after_extremum_detection"] = copy.deepcopy(candidats)

        ## BONUS EVENTUEL ICI

        # Filtrage des points sur les arêtes
        Log.debug(str(len(candidats)) + " points", 1)
        candidats = _filtrerPointsArete(candidats)
        if analyseur:
            elements["kp_after_hessian_filter"] = copy.deepcopy(candidats)

        # Assignation de l'orientation des points
        Log.debug(str(len(candidats)) + " points", 1)
        candidats = _assignOrientation(candidats)
        if analyseur:
            elements["kp_after_orientation_assignation"] = copy.deepcopy(candidats)

        # Packaging des points clés et des outils d'analyse
        if analyseur:
            analyseur.finalKeypoints = copy.deepcopy(candidats)
            analyseur.elements = elements
            pyramid_analyzer.addOctaveAnalyzer(analyseur)

        Log.debug(str(len(candidats)) + " points", 1)

        return candidats

    @staticmethod
    def descriptionPointsCles(image_initiale, points_cles):
        rows, cols = ImageManager.getDimensions(image_initiale)
        descripteurs = []

        for (row, col, sigma, a) in points_cles:
            # On élimine les points clés trop pret du bord
            if not (row < 9 or col < 9 or rows - row < 9 or cols - col < 9):

                # On fait une rotation de l'image
                image_travail = ImageManager.rotate(image_initiale, -a * 180 / np.pi, (row, col))

                # On dessine un carré de coté 16x16
                zone_etude_g = image_travail[(row - 8):(row + 8), (col - 8) - 1:(col + 8) - 1]
                zone_etude_d = image_travail[(row - 8):(row + 8), (col - 8) + 1:(col + 8) + 1]
                zone_etude_h = image_travail[(row - 8) - 1:(row + 8) - 1, (col - 8):(col + 8)]
                zone_etude_b = image_travail[(row - 8) + 1:(row + 8) + 1, (col - 8):(col + 8)]

                zone_etude_g1, zone_etude_g2 = zone_etude_d - zone_etude_g, zone_etude_b - zone_etude_h

                # TODO : Fenètre gaussienne

                # Calcul des amplitude des gradients et de l'orientation
                M = np.sqrt(np.power(zone_etude_g1, 2) + np.power(zone_etude_g2, 2))
                A = np.arctan2(zone_etude_g1, zone_etude_g2)
                A = (A + 2 * np.pi) % (2 * np.pi)  # Opération permettant de revenir dans l'interval [0:2pi]

                # On fait l'étude sur chaque carrés de coté 4x4 contenus dans la zone de travail
                H_angle = np.linspace(0, 2 * np.pi, 8)
                H_container = []
                for i in range(4):
                    for j in range(4):
                        # On étudie un carré de coté 4x4
                        As = A[i * 4:i * 4 + 4, j * 4:j * 4 + 4]
                        Ms = M[i * 4:i * 4 + 4, j * 4:j * 4 + 4]

                        Mf, Af = Ms.flat, As.flat

                        H = [0.0] * 8

                        for k, angle in enumerate(As.flat):
                            for l, an in enumerate(H_angle):
                                if angle < an:
                                    H[l] += float(Mf[k])
                                    break

                        H_container.append(H)

                # On concatène les histogrammes
                H_final = H_container[0]
                for elt in H_container[1::]:
                    H_final = H_final + elt

                H_final = np.array(H_final)
                # On normalise
                H_final = H_final / float(np.max(H_final))

                # On plafonne a 0.2
                for k in range(len(H_final)):
                    if H_final[k] > 0.2:
                        H_final[k] = 0.2

                #  On renormalise
                H_final = H_final / float(np.max(H_final))

                descripteur = np.concatenate((np.array([row, col]), H_final))
                descripteurs.append(descripteur)

        #print(descripteurs)

        return descripteurs
