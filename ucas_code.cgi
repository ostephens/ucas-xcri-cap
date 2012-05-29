#!/usr/bin/perl -w
use strict;
use LWP::UserAgent;
use HTML::Parser;
use CGI;
use CGI::Carp qw ( fatalsToBrowser );
use Data::Dumper;
use XML::Writer;


my $ucas_base_url = "http://search.ucas.com";
my $ucas_path;
my $course_url;
my $course_code;
my $course_results;
my $course_details;
my $stateID;
my $format = "";
my $catalogue_year = "";
my %results_set;
my $institution_code;
my $institution_name;
my $data_type;
my $catalogue_code;
my $writer = XML::Writer->new(DATA_MODE => 1, DATA_INDENT => 5);

#Declare a LWP UserAgent we can use
my $ua = LWP::UserAgent->new;
$ua->agent("meanboyfriend.com/1.0");

my $query = new CGI;

$format = $query->param('format');
$course_code = $query->param('course_code');
$catalogue_year = $query->param('catalogue_year');
$stateID = $query->param('stateID');

&sanitise_parameters;
if (!$stateID) {
	$stateID = get_stateID($catalogue_year);
	}

$course_url = build_course_url($course_code, $stateID);
$course_results = get_html($course_url); #fetch UCAS search results for course

#check if service timed out, and if so get a new stateid before trying again
if ( $course_results =~ m/Service timed out/i ) {
	$stateID = get_stateID($catalogue_year);
	$course_url = build_course_url($course_code, $stateID);
	$course_results = get_html($course_url); #fetch UCAS search results for course
}
if ( $course_results =~ m/No courses found, please try again./i ) {
	&open_results;
	$writer->startTag("error");
	$writer->characters("No Courses found");
	$writer->endTag("error");
	&close_results;
	exit;
}	
	
$course_details = parse_ucas_results($course_results); #find relevant information from results page

$ucas_path = "/cgi-bin/hsrun/search/search/StateId/".$stateID."/HAHTpage/search.";

if ($format eq 'xcri-cap') {
	&output_xcricap;
}
else {
#Output successful results
&open_results;
&output_results;
&close_results;
}

sub sanitise_parameters {
	if ( !($catalogue_year =~ m/^[0-9]{4}$/i) ) {
		$catalogue_year = "";
	}

	if ( $course_code =~ m/^\w{1,4}$/i ) {
		return;
		}

	&open_results;
	$writer->startTag("error");
	$writer->characters("Invalid course code");
	$writer->endTag("error");
	&close_results;
	exit;
}

sub get_stateID {

	my $catalogue_year = $_[0];

	my $course_search_url = $ucas_base_url.'/cgi-bin/hsrun/search/search/search.hjx;start=search.HsCodeSearch.run?y='.$catalogue_year;

	my $response_html = get_html($course_search_url);

	if ($response_html =~ m/StateID\/(\S{29}-\S{4})\//i) { 
		return $1;
        	}

	&open_results;
	$writer->startTag("error");
	$writer->characters("Could not get UCAS Catalogue StateID");
	$writer->endTag("error");
	&close_results;
	exit;
}

sub build_course_url {

	my $course_code = $_[0];
	my $stateID = $_[1];

	my $course_url = $ucas_base_url.'/cgi-bin/hsrun/search/search/StateId/'.$stateID.'/HAHTpage/search.HsCodeSearch.submitForm?cmbInst=&txtJacsCode='.$course_code;
	return $course_url;
}

sub parse_ucas_results {
	my $p = HTML::Parser->new(api_version => 3,
			start_h => [\&a_start_handler, "self,tagname,attr"],
			report_tags => [qw(a)],
			);
	$p->parse(shift || die) || die $!;
}

sub a_start_handler {

    my($self, $tag, $attr) = @_;
    return unless $tag eq "a";
    return unless exists $attr->{href};
    return unless $attr->{href} =~ m/.*\?[n|i]\=.*/i;

    if ($attr->{href} =~ m/.*\?n\=(.*)/i) {
	$data_type = "course";
	$catalogue_code = $1;
        }
    elsif ($attr->{href} =~ m/.*\?i\=(.*)/i) {
	$data_type = "institution";
	$institution_code = $1;	
        }
    $self->handler(text  => [], '@{dtext}' );
    $self->handler(end   => \&a_end_handler, "self,tagname");
}

sub a_end_handler {

    my($self, $tag) = @_;
    my $text = join("", @{$self->handler("text")});
    $text =~ s/^\s+//;
    $text =~ s/\s+$//;
    $text =~ s/\s+/ /g;
    if ($data_type eq "course") {
	push @{ $results_set{$institution_code} }, $catalogue_code;
	push @{ $results_set{$institution_code} }, $text;
	}
	elsif ($data_type eq "institution") {
	$institution_name = $text;
	$results_set{$institution_code} = [$institution_name];
	}
	else {}
    $self->handler("text", undef);
    $self->handler("start", \&a_start_handler);
    $self->handler("end", undef);
}


sub get_html {
	my $url = $_[0];
	my $response;

# Create a request
	my $req = HTTP::Request->new(GET => $url);
	my $res = $ua->request($req);

# Check if successful or not
	if ($res->is_success) {
		$response = $res->content;
		return $response;
        	}
	&open_results;
	$writer->startTag("error");
	$writer->characters("UCAS Code fetch get HTML failed: ".$url." : ".$res->status_line);
	$writer->endTag("error");
	&close_results;
	exit;
}

sub open_results {

	print "Content-type: text/xml\n\n";
	$writer->xmlDecl('UTF-8');
	$writer->startTag('ucas_course_results', 'course_code' => $course_code, 'catalogue_year' => $catalogue_year, 'ucas_stateid' => $stateID);

}

sub close_results {
	$writer->endTag('ucas_course_results');
	$writer->end();
}

sub output_results {
	for my $inst_code ( keys (%results_set) ) {
		$writer->startTag('institution', 'code' => $inst_code, 'name' => $results_set{$inst_code}->[0]);
		$writer->startTag('inst_ucas_url');
		$writer->characters("http://www.ucas.com/students/choosingcourses/choosinguni/instguide/".substr(lc($inst_code),0,1)."/".lc($inst_code));
		$writer->endTag('inst_ucas_url');
		for (my $i = 1; $i < ($#{ $results_set{$inst_code} }); $i+=2 ) {
			$writer->startTag('course', 'ucas_catalogue_id' => $results_set{$inst_code}->[$i]);
			$writer->startTag('course_ucas_url');
			$writer->characters($ucas_base_url.$ucas_path."HsDetails.run?n=".$results_set{$inst_code}->[$i]);
			$writer->endTag('course_ucas_url');
			$writer->startTag('name');
			$writer->characters($results_set{$inst_code}->[$i+1]);
			$writer->endTag('name');
			$writer->endTag('course');
			}
		$writer->endTag('institution');
		}
}

sub output_xcricap {
	my ($sec,$min,$hour,$mday,$mon,$year,$wday,$yday,$isdst) = localtime(time);
	$year += 1900;
	$mon += 1;
	my $timestamp = $year."-".sprintf("%02d",$mon)."-".$mday."T".$hour.":".$min.":".$sec;
	print "Content-type: text/xml\n\n";
	$writer->xmlDecl('UTF-8');
	#Using the example from http://www.xcri.org/wiki/index.php/Sample_SQL_Server_2005_code_for_generating_XCRI_XML_from_a_simplified_relational_course_database
	#Need to generate the correct date into a variable and put it into the 'generated' id
	$writer->startTag('catalog', 'xmlns' => "http://xcri.org/profiles/catalog", 'xmlns:dc' => "http://purl.org/dc/elements/1.1/", 
	'xmlns:xhtml' => "http://www.w3.org/1999/xhtml", 'xmlns:xcri' => "http://xcri.org/profiles/catalog", 
	'generated' => $timestamp);
	foreach my $inst_code (keys (%results_set) ) {
		$writer->startTag('provider', 'xmlns' => "http://xcri.org/profiles/catalog", 'xmlns:dc' => "http://purl.org/dc/elements/1.1/",
		'xmlns:xhtml' => "http://www.w3.org/1999/xhtml", 'xmlns:xcri' => "http://xcri.org/profiles/catalog");
		#Is the UCAS institution code a recognised identifier?
		#Can we do something like <identifier xsi:type="ukrlp:UKPRN">10006841</identifier> from Boxcrip project?
		$writer->startTag('identifier');
		$writer->characters($inst_code);
		$writer->endTag('identifier');
		$writer->startTag('title');
		$writer->characters($results_set{$inst_code}->[0]);
		$writer->endTag('title');
		#Would it make sense to provide the UCAS Institution URL here, or should this only be the actual institution URL for XCRI-CAP
		$writer->startTag('url');
		$writer->characters($ucas_base_url.$ucas_path."HsInstDetails.run?i=".$inst_code);
		$writer->endTag('url');
				for (my $i = 1; $i < ($#{ $results_set{$inst_code} }); $i+=2 ) {
			$writer->startTag('course', 'xmlns' => "http://xcri.org/profiles/catalog", 'xmlns:dc' => "http://purl.org/dc/elements/1.1/",
			'xmlns:xhtml' => "http://www.w3.org/1999/xhtml", 'xmlns:xcri' => "http://xcri.org/profiles/catalog");
			$writer->startTag('identifier');
			$writer->characters($results_set{$inst_code}->[$i]);
			$writer->endTag('identifier');
			$writer->startTag('title');
			$writer->characters($results_set{$inst_code}->[$i+1]);
			$writer->endTag('title');
			$writer->startTag('url');
			$writer->characters($ucas_base_url.$ucas_path."HsDetails.run?n=".$results_set{$inst_code}->[$i]);
			$writer->endTag('url');
			#Should/can we scrape a description from UCAS pages to put here?
			#Other elements to look at are:
			#	Qualification/level
			#	Qualification/title (e.g. BSc)
			#	Presentation/identifier
			#	Presentation/start (date)
			#	Presentation/study mode (part-time/full-time etc.)
			#	Note, can be multiple presentations per course
			#	dc:subject (possibly decode this from JACS/UCAS code?)
			$writer->endTag('course');
			}
		$writer->endTag('provider');
	}
	$writer->endTag('catalog');
	$writer->end();
}
	
