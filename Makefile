# vim: set noet sw=4 ts=4 fileencoding=utf-8:

# External utilities
PYTHON=python3
PIP=pip
PYTEST=pytest
TWINE=twine
PYFLAGS=
MSGINIT=msginit
MSGMERGE=msgmerge
MSGFMT=msgfmt
XGETTEXT=xgettext
DEST_DIR=/

# Find the location of the GObject introspection libs and cairo (required for
# the develop target)
GI:=$(wildcard /usr/lib/python3/dist-packages/gi)
GOBJECT:=
GLIB:=

# Calculate the base names of the distribution, the location of all source,
# documentation, packaging, icon, and executable script files
NAME:=$(shell $(PYTHON) $(PYFLAGS) setup.py --name)
WHEEL_NAME:=$(subst -,_,$(NAME))
VER:=$(shell $(PYTHON) $(PYFLAGS) setup.py --version)
PY_SOURCES:=$(shell \
	$(PYTHON) $(PYFLAGS) setup.py egg_info >/dev/null 2>&1 && \
	cat $(WHEEL_NAME).egg-info/SOURCES.txt | grep -v "\.egg-info"  | grep -v "\.mo$$")
DOC_SOURCES:=docs/conf.py \
	$(wildcard docs/*.png) \
	$(wildcard docs/*.svg) \
	$(wildcard docs/*.dot) \
	$(wildcard docs/*.mscgen) \
	$(wildcard docs/*.gpi) \
	$(wildcard docs/*.rst) \
	$(wildcard docs/*.pdf)
SUBDIRS:=

# Calculate the name of all outputs
DIST_WHEEL=dist/$(WHEEL_NAME)-$(VER)-py3-none-any.whl
DIST_TAR=dist/$(NAME)-$(VER).tar.gz
DIST_ZIP=dist/$(NAME)-$(VER).zip
POT_FILE=po/$(NAME).pot
PO_FILES:=$(wildcard po/*.po)
MO_FILES:=$(patsubst po/%.po,po/mo/%/LC_MESSAGES/$(NAME).mo,$(PO_FILES))
MAN_PAGES=\
	man/pemmican-cli.1 \
	man/pemmican-mon.1 \
	man/pemmican-reset.1


# Default target
all:
	@echo "make install - Install on local system"
	@echo "make develop - Install symlinks for development"
	@echo "make pot - Update translation template and sources"
	@echo "make mo - Generate translation files"
	@echo "make test - Run tests"
	@echo "make doc - Generate HTML and PDF documentation"
	@echo "make source - Create source package"
	@echo "make wheel - Generate a PyPI wheel package"
	@echo "make zip - Generate a source zip package"
	@echo "make tar - Generate a source tar package"
	@echo "make dist - Generate all packages"
	@echo "make clean - Get rid of all generated files"
	@echo "make release - Create and tag a new release"
	@echo "make upload - Upload the new release to repositories"

install: $(SUBDIRS)
	$(PYTHON) $(PYFLAGS) setup.py install --root $(DEST_DIR)

doc: $(DOC_SOURCES)
	$(MAKE) -C docs clean
	$(MAKE) -C docs html
	$(MAKE) -C docs epub
	$(MAKE) -C docs latexpdf
	$(MAKE) $(MAN_PAGES)

preview:
	$(MAKE) -C docs preview

source: $(DIST_TAR) $(DIST_ZIP)

wheel: $(DIST_WHEEL)

zip: $(DIST_ZIP)

tar: $(DIST_TAR)

dist: $(DIST_WHEEL) $(DIST_TAR) $(DIST_ZIP)

pot: $(POT_FILE) $(PO_FILES)

mo: $(MO_FILES)

develop:
	@# These have to be done separately to avoid a cockup...
	$(PIP) install -U setuptools
	$(PIP) install -U pip
	$(PIP) install -U twine
	$(PIP) install -U tox
	$(PIP) install -e .[gui,doc,test]
	@# If we're in a venv, link the system's GObject Introspection (gi) into it
ifeq ($(VIRTUAL_ENV),)
	@echo "Virtualenv not detected! You may need to link gi manually"
else
ifeq ($(GI),)
	@echo "ERROR: gi not found. Install the python{,3}-gi packages"
else
	ln -sf $(GI) $(VIRTUAL_ENV)/lib/python*/site-packages/
endif
ifneq ($(GLIB),)
	ln -sf $(GLIB) $(VIRTUAL_ENV)/lib/python*/site-packages/
endif
ifneq ($(GOBJECT),)
	ln -sf $(GOBJECT) $(VIRTUAL_ENV)/lib/python*/site-packages/
endif
endif

test:
	$(PYTEST)

clean:
	rm -fr dist/ build/ man/ .pytest_cache/ .mypy_cache/ $(WHEEL_NAME).egg-info/ tags .coverage
	for dir in $(SUBDIRS); do \
		$(MAKE) -C $$dir clean; \
	done
	find $(CURDIR) -name "*.pyc" -delete
	find $(CURDIR) -name "__pycache__" -delete

tags: $(PY_SOURCES)
	ctags -R --exclude="build/*" --exclude="docs/*" --languages="Python"

lint: $(PY_SOURCES)
	pylint $(WHEEL_NAME)

$(SUBDIRS):
	$(MAKE) -C $@

$(MAN_PAGES): $(DOC_SOURCES)
	$(MAKE) -C docs man
	mkdir -p man/
	cp build/man/*.[0-9] man/

$(POT_FILE): $(PY_SOURCES)
	$(XGETTEXT) -o $@ $(filter %.py,$^) $(filter %.ui,$^)

po/%.po: $(POT_FILE)
	$(MSGMERGE) -U $@ $<

po/mo/%/LC_MESSAGES/$(NAME).mo: po/%.po
	mkdir -p $(dir $@)
	$(MSGFMT) $< -o $@

$(DIST_TAR): $(PY_SOURCES) $(SUBDIRS)
	$(PYTHON) $(PYFLAGS) setup.py sdist --formats gztar

$(DIST_ZIP): $(PY_SOURCES) $(SUBDIRS)
	$(PYTHON) $(PYFLAGS) setup.py sdist --formats zip

$(DIST_WHEEL): $(PY_SOURCES) $(SUBDIRS)
	$(PYTHON) $(PYFLAGS) setup.py bdist_wheel

release:
	$(MAKE) clean
	test -z "$(shell git status --porcelain)"
	git tag -s v$(VER) -m "Release $(VER)"
	git push origin v$(VER)

upload: $(DIST_TAR) $(DIST_WHEEL)
	$(TWINE) check $(DIST_TAR) $(DIST_WHEEL)
	$(TWINE) upload $(DIST_TAR) $(DIST_WHEEL)

.PHONY: all install develop test doc source wheel zip tar dist clean tags release upload $(SUBDIRS)
