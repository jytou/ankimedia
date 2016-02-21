# import the main window object (mw) from ankiqt
from aqt import mw
# import the "show info" tool from utils.py
from aqt.utils import showInfo, showWarning, askUser
# import all of the Qt GUI library
from aqt.qt import *
import re, urllib2, os, unicodedata, uuid, time
from shutil import copyfile
import filecmp
import logging

class DecksDialog(QDialog):
	def __init__(self, parent = None):
		super(DecksDialog, self).__init__(parent)
		self.resize(320, 240)
		self.setWindowTitle("Select a Deck")

		layout = QVBoxLayout(self)

		layout.addWidget(QLabel("Select your deck"))

		self.combo = QComboBox()
		decks = list()
		for deckName in mw.col.decks.allNames():
			if deckName:
				decks.append(deckName)
		for deckName in sorted(decks):
			self.combo.addItem(deckName)
		layout.addWidget(self.combo)

		layout.addWidget(QLabel("Root of the http server (no trailing / )"))
		self.url = QLineEdit("http://my.website.com/anki")
		layout.addWidget(self.url)

		layout.addWidget(QLabel("Alias for the deck (should be unique on the server)"))
		self.alias = QLineEdit("")
		layout.addWidget(self.alias)

		layout.addWidget(QLabel("Select the destination folder (no trailing / )"))
		self.folder = QLineEdit("c:/temp/anki")
		layout.addWidget(self.folder)

		self.normalizeNames = QCheckBox("Normalize File Names (recommended)")
		self.normalizeNames.setCheckState(Qt.Checked)
		layout.addWidget(self.normalizeNames)

		buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, Qt.Horizontal, self)
		buttons.accepted.connect(self.accept)
		buttons.rejected.connect(self.reject)
		layout.addWidget(buttons)

	def getDeck(self):
		return self.combo.currentText()

	def getDestDir(self):
		destDir = str(self.folder.text()).strip()
		if destDir.endswith("/"):
			destDir = destDir[:-1]
		return destDir

	def getUrl(self):
		url = str(self.url.text()).strip()
		if url.endswith("/"):
			url = url[:-1]
		return url

	def getDeckAlias(self):
		return str(self.alias.text()).strip()

	def isNormalizeNames(self):
		return self.normalizeNames.checkState() == Qt.Checked

class LongMessageDialog(QDialog):
	def __init__(self, title, message, parent = None):
		super(LongMessageDialog, self).__init__(parent)
		self.resize(320, 420)
		self.setWindowTitle(title)

		layout = QVBoxLayout(self)
		layout.addWidget(QTextEdit(message))
		buttons = QDialogButtonBox(QDialogButtonBox.Ok, Qt.Horizontal, self)
		buttons.accepted.connect(self.accept)
		layout.addWidget(buttons)

class VerifyDialog(QDialog):
	def __init__(self, parent = None):
		super(VerifyDialog, self).__init__(parent)
		self.resize(320, 200)
		self.setWindowTitle("Check external medias")

		layout = QVBoxLayout(self)

		layout.addWidget(QLabel("Root of the http server (no trailing / )"))
		self.url = QLineEdit("http://my.website.com/anki")
		layout.addWidget(self.url)

		layout.addWidget(QLabel("Select the destination folder (no trailing / )"))
		self.folder = QLineEdit("c:/temp/anki")
		layout.addWidget(self.folder)

		buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, Qt.Horizontal, self)
		buttons.accepted.connect(self.accept)
		buttons.rejected.connect(self.reject)
		layout.addWidget(buttons)

	def getDestDir(self):
		destDir = str(self.folder.text()).strip()
		if destDir.endswith("/"):
			destDir = destDir[:-1]
		return destDir

	def getUrl(self):
		url = str(self.url.text()).strip()
		if url.endswith("/"):
			url = url[:-1]
		return url

def verifyExternalizedMedia():
	w = VerifyDialog()
	result = w.exec_()
	if result != QDialog.Accepted:
		return
	url = w.getUrl()
	destDir = w.getDestDir()
	nids = mw.col.db.list("select distinct notes.id from notes where lower(notes.flds) like '%%http%%'")
	mw.progress.start(max=len(nids), min=0, immediate=True)
	replacers = [SoundReplacer(), ImageReplacer(True), ImageReplacer(False)]
	notexist = list()
	notesVerified = 0
	mediasVerified = 0
	for nid in nids:
		note = mw.col.getNote(nid)
		notesVerified += 1
		for field, value in note.items():
			for replacer in replacers:
				for media in re.findall(replacer.getPattern(), value):
					media = media[0]
					if media.startswith(url):
						mediasVerified += 1
						if not os.path.exists(destDir + media[len(url):]):
							notexist.append(media)
		mw.progress.update()
	mw.progress.finish()
	if notexist:
		LongMessageDialog("Verification results", "The following don't exist:<br>%s" % ("<br>").join(notexist)).exec_()
	else:
		showInfo("Perfect, all media exist (%d notes verified, %d media verified)" % (notesVerified, mediasVerified))

def appendValToMap(mymap, mykey, myval):
	if not mykey in mymap:
		mymap[mykey] = set()
	mymap[mykey].add(myval)

class SoundReplacer:
	def __init__(self):
		self.pattern = re.compile('\[sound:((.)+?)\]', re.IGNORECASE)
	def getPattern(self):
		return self.pattern
	def replace(self, oldname, newname, url, value):
		return value.replace("[sound:" + oldname + "]", "[sound:" + url + "/" + newname + "]")

class ImageReplacer:
	def __init__(self, doublequote):
		self.doublequote = doublequote
		self.startpattern = '<img src='
		self.endpattern = '[ ]*?[/]?>'
		self.startreplace = self.startpattern
		self.endreplace = '/>'
		self.quote = '"' if doublequote else "'"
		#self.pattern = re.compile(self.startpattern + self.quote + '((.)+?)' + self.quote + self.endpattern, re.IGNORECASE)
		self.pattern = re.compile(self.startpattern + self.quote + '((.)+?)' + self.quote, re.IGNORECASE)
	def getPattern(self):
		return self.pattern
	def replace(self, oldname, newname, url, value):
		# Beware: we have to escape special characters otherwise we'll feed in an unwanted expression
		#mypattern = re.compile(self.startpattern + self.quote + re.sub(r'\*\(\)\!\^\$\[\]\{\}\|', r'\\\1', re.escape(oldname)) + self.quote + self.endpattern, re.IGNORECASE)
		#return re.sub(mypattern, self.startreplace + self.quote + url + "/" + newname + self.quote + self.endreplace, value)
		mypattern = re.compile(self.startpattern + self.quote + re.sub(r'\*\(\)\!\^\$\[\]\{\}\|', r'\\\1', re.escape(oldname)) + self.quote, re.IGNORECASE)
		return re.sub(mypattern, self.startreplace + self.quote + url + "/" + newname + self.quote, value)

def externalizeMedia():
	# get the number of cards in the current collection, which is stored in the main window
	# Choose which deck will be impacted
	emlogger = logging.getLogger('externalizeMedia')
	lh = logging.FileHandler(os.path.abspath(os.path.join(os.path.join(str(mw.col.media.dir()), os.pardir), "extmedia.log")))
	lh.setLevel(logging.INFO)
	lh.setFormatter(logging.Formatter('%(levelname)s - %(message)s'))
	emlogger.setLevel(logging.INFO)
	emlogger.addHandler(lh)

	w = DecksDialog()
	result = w.exec_()
	if result != QDialog.Accepted:
		return
	deckid = mw.col.decks.id(w.getDeck())
	if len(w.getUrl()) < 8:
		showWarning("Url must not be empty")
		return
	if not w.getDestDir():
		showWarning("Destination directory must not be empty")
		return

	normalizeNames = w.isNormalizeNames()
	deckAlias = w.getDeckAlias()
	if deckid:
		deck = mw.col.decks.get(deckid)
	if not deckAlias:
		deckAlias = str(deckid)
	url = w.getUrl() + "/" + deckAlias
	destDir = w.getDestDir() + "/" + deckAlias
	if not os.path.exists(destDir):
		try:
			os.mkdir(destDir)
		except IOError:
			showWarning("Could not create destination directory %s" % destDir)
			return
	elif not os.path.isdir(destDir):
		showWarning("The destination directory %s exists, but it is a file" % destDir)
		return

	cardCount = "Could not get deck!"
	if deck:
		affectedCount = 0
		try:
			# First build dictionaries of who is using what to make sure we don't delete media used by other decks
			nids = mw.col.db.list("select distinct notes.id from notes where (lower(notes.flds) like '%%[sound:%%' or lower(notes.flds) like '%%img%%')")
			decknids = mw.col.db.list("select distinct notes.id from notes inner join cards on notes.id = cards.nid where cards.did = %d and (lower(notes.flds) like '%%[sound:%%' or lower(notes.flds) like '%%img%%')" % deckid)
			mw.progress.start(max=len(nids) + len(decknids), min=0, immediate=True)
			replacers = [SoundReplacer(), ImageReplacer(True), ImageReplacer(False)]
			note2medias = {}
			media2notes = {}
			renames = {}
			for nid in nids:
				note = mw.col.getNote(nid)
				for field, value in note.items():
					for replacer in replacers:
						for media in re.findall(replacer.getPattern(), value):
							media = media[0]
							if not "://" in media:
								appendValToMap(note2medias, nid, media)
								appendValToMap(media2notes, media, nid)
								emlogger.info("Found media %s in note %d (field %s)" % (media, nid, field))
				mw.progress.update()

			# Now fetch only the notes that we need in the selected deck
			mediaDir = str(mw.col.media.dir())
			# For each node id, fetch the associated medias
			abort = False
			for nid in decknids:
				if nid in note2medias:
					# The node id has medias, treat it
					# Manage the media first: make sure that we can copy/move them
					okmedias = {}
					for media in note2medias[nid]:
						srcFile = mediaDir + "/" + media
						if not os.path.exists(srcFile):
							continue # there is no such file, we can't do anything with it
						copyError = False
						if media in renames:
							okmedias[media] = renames[media] # We've already dealt with this one somewhere else
						else:
							if normalizeNames:
								splitMedia = media.split('.')
								mediaName = u"".join([c for c in unicodedata.normalize('NFKD', splitMedia[0]) if not unicodedata.combining(c)])
								if len(mediaName) < 2:
									# Let's make some uuid instead
									mediaName = str(uuid.uuid4())
								splitMedia[0] = mediaName
								normalizedMedia = ('.').join(splitMedia)
								destName = normalizedMedia # The destination file name - it may be renamed if it already exists and is different
							else:
								destName = media

							newName = destName
							destFile = destDir + "/" + destName # the default name
							renameIndex = 0
							while os.path.exists(destFile) and not filecmp.cmp(srcFile, destFile):
								# That's not good, we have to rename the file
								renameIndex += 1
								splitfile = normalizedMedia.split('.')
								splitfile[0] += str(renameIndex)
								newName = ('.').join(splitfile)
								destFile = destDir + "/" + newName
							if renameIndex > 0:
								# We have renamed it
								destName = newName
								renames[media] = newName
								emlogger.info("Renaming media %s to %s" % (media, newName))
							# Copy/move the media to the destination
							if not os.path.exists(destFile):
								emlogger.info("Copy %s -> %s" % (srcFile, destFile))
								try:
									copyfile(srcFile, destFile)
									okmedias[media] = destName
								except IOError:
									emlogger.error("Copy error for file %s into %s" % (media, destFile))
									if media in renames:
										del renames[media] # we may fail again, but better than deleting it later...
									if not askUser("Copying file %s has failed. Do you want to continue? (will abort if no)"):
										return
									copyError = True
							else:
								okmedias[media] = destName
						if not copyError:
							media2notes[media].remove(nid)
							if not media2notes[media]:
								# It is empty: remove the file (only if the copy succeeded)
								emlogger.info("Removing file %s" % srcFile)
								try:
									os.remove(srcFile)
								except IOError:
									emlogger.error("Could not delete file %s" % srcFile)

					note = mw.col.getNote(nid)
					affected = False # gets True if the note has changed
					for field, value in note.items():
						fieldAffected = False # gets True if the field was affected by a change
						for replacer in replacers: # For every replacer, do replacements
							for media in re.findall(replacer.getPattern(), value):
								media = media[0]
								if media in okmedias:
									emlogger.info("Replacing %s in note %d (%s)" % (media, nid, value))
									newvalue = replacer.replace(media, okmedias[media], url, value)
									if newvalue != value:
										affected = True
										fieldAffected = True
										value = newvalue
						if fieldAffected:
							note[field] = value

					if affected:
						note.flush(time.time())
						affectedCount += 1
				mw.progress.update()
		finally:
			if affectedCount > 0:
				mw.col.media.findChanges()
			mw.progress.finish()
			showInfo("Deck: %s\nNotes affected: %d" % (deck["name"], affectedCount))

# create a new menu item, "test"
action = QAction("Externalize Media", mw)
# set it to call testFunction when it's clicked
mw.connect(action, SIGNAL("triggered()"), externalizeMedia)
# and add it to the tools menu
mw.form.menuTools.addAction(action)

action = QAction("Verify Externalized Media", mw)
# set it to call testFunction when it's clicked
mw.connect(action, SIGNAL("triggered()"), verifyExternalizedMedia)
# and add it to the tools menu
mw.form.menuTools.addAction(action)

# DeckManager: allIds, all, allNames, byName, cids, col, current, get, id