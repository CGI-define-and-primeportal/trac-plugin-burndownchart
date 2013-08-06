$(document).ready(function(){

  // Expects date as a string in yyyy-mm-dd format, with a time added for 
  // greater accuracy.
  window.addTime = function(date){
    var formatted_date = date + ' 12:01AM'
    return formatted_date
  };

  // Function which returns a two dimensional array. Each array has a 
  // date and value, with the value reflecting some kind of work either 
  // remaining or completed on that day
  window.dataSeries = function(curvedata){
    var series_data = new Array;
    for (var i=0; i < curvedata.length; i++) {
      series_data.push([addTime(curvedata[i][0]), curvedata[i][1]])
    }
    return series_data
  };

  // Curve data needed for jqPlot series
  var burndowncurve = dataSeries(burndowndata);  // Burndown Data
  var teameffortcurve = dataSeries(teameffortdata);  // Team Effort Data
  var idealcurve = dataSeries(idealcurvedata);  // Ideal Curve Data

  // Makes the jqPlot resize when the window dimensions change
  $(window).on('debouncedresize', function() {
        plot1.replot( { resetAxes: true } );
  });

  // Calculate the interval between x-axis dates
  var days_in_milestone = idealcurve.length
  if (days_in_milestone < 20) {
    var xaxis_interval = '1 day';
  }
  else if (days_in_milestone < 30) {
    var xasis_interval = '2 days';
  }
  else if (days_in_milestone < 40) {
    var xasis_internval = '1 week';
  }
  else if (days_in_milestone > 120) {
    var xaxis_interval = '1 month'
  }

  // Render the jqPlot burn down chart
  var plot1 = $.jqplot('chart1', [burndowncurve, teameffortcurve, idealcurve], {
    axesDefaults: {
      tickRenderer: $.jqplot.CanvasAxisTickRenderer,
      tickOptions: {
        fontFamily: 'Open Sans',
        fontSize: '8pt'
      },
      labelOptions: {
        textColor: '#0066CC',
        fontFamily: 'Open Sans',
        fontSize: '10pt',
        fontWeight: 'normal'
      }
    },
    axes: {
      xaxis: {
        renderer:$.jqplot.DateAxisRenderer,
        tickOptions:{formatString: '%d %b'},
        label: 'Days in Milestone',
        tickInterval:xaxis_interval,
        min: chartdata['start_date'],
        max: chartdata['end_date'],
      },
      yaxis: {
        label: 'Effort (' + chartdata['effort_units'] +')',
        min: 0,
        labelRenderer: $.jqplot.CanvasAxisLabelRenderer
      }
    }, 
    highlighter: {
      show: true, 
      tooltipAxes: 'both',
      sizeAdjust: 7.5,
      fadeTooltip: true,
      tooltipFadeSpeed: 'fast',
      tooltipAxes: 'xy',
      formatString: '%s - %s ' + chartdata['effort_units'],
      },
    series:[
            {color:'#5FAB78', label: 'Remaining effort'},
            {label: 'Team effort'},
            {label: 'Ideal effort', showMarker: false},
           ],
    legend: {
      show: true,
      }
  });
});